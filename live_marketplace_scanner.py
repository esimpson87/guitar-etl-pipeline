#!/usr/bin/env python3
"""
live_marketplace_scanner.py
Real-time multi-platform music gear arbitrage scanner (Guitars, Pedals, Microphones, Amplifiers) with:
  1. Category + Brand Filtering (Guitars, Guitar Pedals & Effects, Microphones & Studio Audio, Amplifiers & Heads)
  2. Specific Model Signature Extraction from listing Title + Description + Metadata
  3. Live Per-Listing Exact-Model Reverb Used Comp Lookup (Strictly excludes Brand New, matches Condition Tier)
  4. Recommended Offer Price (25% Target Net ROI) & Suggested Maximum Offer / Max Auction Bid Ceiling (12% Net ROI Floor)
  5. Multi-Layer Deduplication (Title Fingerprinting + Any-Shared-Photo-Hash Detection across posts)
  6. Deep Post Authenticity & Condition Investigator (Partscaster/Replica/DIY kit detection, Untested/Repair reserve)
"""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import html
import re
import statistics
import sys
from typing import Any, Dict, List, Optional, Set, Tuple
import urllib.parse
import requests

REVERB_FEE_RATE = 0.0819
REVERB_FIXED_FEE_USD = 0.49
DEFAULT_BENCH_SETUP_USD = 35.00

# ==============================================================================
# MULTI-CATEGORY & BRAND CATALOG
# ==============================================================================

CATEGORY_CATALOG: Dict[str, Dict[str, Any]] = {
    "Guitars": {
        "default_query_suffix": "Guitar",
        "bench_setup_usd": 35.00,
        "untested_setup_usd": 55.00,
        "default_reverb_ship_usd": 45.00,
        "default_goodwill_ship_usd": 28.00,
        "min_price_usd": 70.00,
        "target_min_profit_usd": 35.00,
        "floor_min_profit_usd": 20.00,
        "brands": [
            "All Brands",
            "Fender",
            "Gibson",
            "Gretsch",
            "Epiphone",
            "PRS",
            "Martin",
            "Taylor",
            "Ibanez",
            "Squier",
            "Yamaha",
            "ESP / LTD",
            "Jackson",
            "Schecter",
            "Guild",
        ],
    },
    "Guitar Pedals & Effects": {
        "default_query_suffix": "Guitar Pedal",
        "bench_setup_usd": 10.00,
        "untested_setup_usd": 15.00,
        "default_reverb_ship_usd": 12.00,
        "default_goodwill_ship_usd": 10.00,
        "min_price_usd": 25.00,
        "target_min_profit_usd": 18.00,
        "floor_min_profit_usd": 10.00,
        "brands": [
            "All Brands",
            "Boss",
            "Strymon",
            "Electro-Harmonix",
            "JHS",
            "MXR",
            "Ibanez",
            "Walrus Audio",
            "EarthQuaker Devices",
            "Keeley",
            "Wampler",
            "TC Electronic",
            "Line 6",
            "Eventide",
            "Chase Bliss",
            "Dunlop",
            "ProCo",
        ],
    },
    "Microphones & Studio Audio": {
        "default_query_suffix": "Microphone",
        "bench_setup_usd": 12.00,
        "untested_setup_usd": 18.00,
        "default_reverb_ship_usd": 14.00,
        "default_goodwill_ship_usd": 12.00,
        "min_price_usd": 30.00,
        "target_min_profit_usd": 20.00,
        "floor_min_profit_usd": 12.00,
        "brands": [
            "All Brands",
            "Shure",
            "Sennheiser",
            "Audio-Technica",
            "Neumann",
            "AKG",
            "Rode",
            "Electro-Voice",
            "Blue",
            "Warm Audio",
            "Beyerdynamic",
            "Aston",
            "sE Electronics",
            "Audix",
            "Telefunken",
        ],
    },
    "Amplifiers & Heads": {
        "default_query_suffix": "Guitar Amplifier",
        "bench_setup_usd": 25.00,
        "untested_setup_usd": 45.00,
        "default_reverb_ship_usd": 55.00,
        "default_goodwill_ship_usd": 34.00,
        "min_price_usd": 50.00,
        "target_min_profit_usd": 35.00,
        "floor_min_profit_usd": 20.00,
        "brands": [
            "All Brands",
            "Fender",
            "Marshall",
            "Vox",
            "Orange",
            "Boss",
            "Mesa Boogie",
            "Peavey",
            "Blackstar",
            "EVH",
            "Roland",
            "Supro",
            "Ampeg",
        ],
    },
}


def build_category_brand_query(
    item_category: str = "Guitars",
    brand: str = "Fender",
    custom_keyword: str = "",
) -> str:
    """Builds a clean search query from item_category, brand, and optional custom sub-model keyword."""
    cat_info = CATEGORY_CATALOG.get(item_category, CATEGORY_CATALOG["Guitars"])
    suffix = cat_info["default_query_suffix"]
    brand_clean = brand.strip() if brand and brand != "All Brands" else ""
    if brand_clean == "ESP / LTD":
        brand_clean = "ESP LTD"
    custom_clean = custom_keyword.strip()

    parts = [p for p in (brand_clean, custom_clean, suffix) if p]
    # Avoid repeating words (e.g. if custom_clean already says 'Pedal' or 'Guitar')
    deduped_words: List[str] = []
    for word in " ".join(parts).split():
        if word.lower() not in [w.lower() for w in deduped_words]:
            deduped_words.append(word)
    return " ".join(deduped_words) if deduped_words else suffix


def infer_category_from_query(query: str) -> str:
    low = query.lower()
    if any(k in low for k in ("pedal", "strymon", "jhs", "mxr", "walrus", "earthquaker", "overdrive", "fuzz", "delay", "reverb pedal", "chorus", "tube screamer", "wah", "cry baby")):
        return "Guitar Pedals & Effects"
    if any(k in low for k in ("microphone", "mic", "shure", "sennheiser", "neumann", "audio-technica", "akg", "rode", "electro-voice", "sm57", "sm58", "sm7b", "condenser")):
        return "Microphones & Studio Audio"
    if any(k in low for k in ("amplifier", "amp", "marshall", "vox", "mesa boogie", "katana", "blues junior", "twin reverb", "deluxe reverb")):
        return "Amplifiers & Heads"
    return "Guitars"


# ==============================================================================
# EXCLUSION & NOISE LISTS
# ==============================================================================

COMMON_EXCLUDE_KEYWORDS = (
    "guitar hero",
    "rock band",
    "xbox",
    "playstation",
    "ps2",
    "ps3",
    "ps4",
    "wii",
    "nintendo",
    "controller",
    "miniature",
    "ornament",
    "pin ",
    "keychain",
    "t-shirt",
    "poster",
    "magazine",
    "empty box",
    "box only",
    "manual only",
    "wall hanger",
    "stand only",
    "strap only",
    "case only",
    "case for",
    "gig bag only",
    "gigbag only",
    "bag for",
    "amp cover",
    "dust cover",
    "watch",
    "chronograph",
    "timepiece",
    "jewelry",
    "bracelet",
    "apparel",
)

GUITAR_ONLY_EXCLUDE_KEYWORDS = (
    "pickguard",
    "pre-wired",
    "prewired",
    "wiring harness",
    "loaded body",
    "body only",
    "neck only",
    "replacement neck",
    "bridge only",
    "tremolo block",
    "tuning peg",
    "tuners only",
    "knob",
    "strings only",
    "guitar case",
    "acoustic case",
    "electric case",
    "hard case",
    "hardshell",
    "hardcase",
    "molded case",
    "pedal",
    "pickup set",
    "pickups only",
    "ukulele",
    "mandolin",
    "banjo",
    "violin",
    "cello",
    "upright bass",
    "double bass",
    "lap steel",
    "unfinished",
    "diy kit",
    "guitar kit",
    "body neck",
    "body and neck",
    "body & neck",
    "guitar body",
    "guitar neck",
    "project body",
    "raw body",
)

PEDAL_EXCLUDE_KEYWORDS = (
    "power supply only",
    "adapter only",
    "patch cable",
    "cables only",
    "pedalboard only",
    "board only",
    "case only",
    "mounting bracket",
    "knobs only",
    "sticker",
    "empty box",
)

MIC_EXCLUDE_KEYWORDS = (
    "mic stand only",
    "stand only",
    "boom arm only",
    "xlr cable",
    "cable only",
    "windscreen only",
    "foam only",
    "pop filter only",
    "shock mount only",
    "shockmount only",
    "clip only",
    "karaoke",
    "toy microphone",
    "for parts",
    "broken",
)

AMP_EXCLUDE_KEYWORDS = (
    "amp cover",
    "cover only",
    "footswitch only",
    "foot switch only",
    "empty cabinet",
    "unloaded cab",
    "empty shell",
    "tubes only",
    "speaker only",
    "handle only",
    "caster",
    "logo badge",
)

NOISE_WORDS = {
    "electric", "acoustic", "guitar", "guitars", "6-string", "6", "string",
    "pedal", "pedals", "effects", "effect", "stompbox", "microphone", "mic", "amplifier", "amp",
    "with", "w/", "w", "ohsc", "case", "hardshell", "hard", "gig", "bag", "gigbag",
    "sunburst", "burst", "black", "white", "red", "blue", "green", "yellow",
    "natural", "blonde", "gold", "silver", "metallic", "olympic", "candy", "apple",
    "cherry", "tobacco", "honey", "amber", "ebony", "wine", "alpine", "vintage",
    "pattern", "hpl", "koa", "spruce", "mahogany", "maple", "rosewood", "pau", "ferro",
    "fingerboard", "fretboard", "neck", "body", "top", "figured", "flamed", "quilted",
    "excellent", "mint", "good", "fair", "condition", "used", "new", "brand",
    "tested", "not", "untested", "working", "great", "nice", "rare",
    "ed", "edition", "series", "collection", "the", "by", "in", "for", "sale",
    "and", "or", "includes", "included", "free", "shipping", "fast", "local", "pickup",
    "cond", "mint", "trade", "survivor", "box", "power", "supply",
}

GENERIC_QUERY_WORDS = {
    "fender", "gibson", "martin", "prs", "ibanez", "epiphone", "squier", "squire",
    "yamaha", "taylor", "gretsch", "jackson", "esp", "ltd", "schecter", "guild",
    "boss", "strymon", "jhs", "mxr", "walrus", "keeley", "wampler", "dunlop", "line",
    "shure", "sennheiser", "neumann", "akg", "rode", "audix", "marshall", "vox", "orange", "peavey",
    "guitar", "guitars", "electric", "acoustic", "bass", "american", "made",
    "pedal", "pedals", "effects", "effect", "microphone", "mic", "amplifier", "amp", "audio",
}

REPLICA_KEYWORDS = (
    "partscaster",
    "guitar builds",
    "custom builds",
    "fender specs",
    "tribute build",
    "replica",
    "clone",
    "copy",
    "chibson",
    "custom build",
    "aftermarket neck",
    "squier body",
    "fender decal",
    "waterslides",
    "waterslide decal",
    "not a fender",
    "not a gibson",
    "unbranded",
    "homage",
    "prs style",
    "strat style",
    "tele style",
    "les paul style",
    "lp style",
    "style guitar",
    "style body",
    "style neck",
    "style electric",
    "style build",
    "diy build",
    "kit build",
    "akusa",
    "counterfeit",
    "fake",
)

REPAIR_RISK_KEYWORDS = (
    "not tested",
    "untested",
    "as is",
    "as-is",
    "for parts",
    "needs repair",
    "needs work",
    "neck crack",
    "headstock crack",
    "headstock repair",
    "repaired headstock",
    "broken",
    "missing strings",
    "no strings",
    "project guitar",
    "crack in",
    "buzz",
    "electronics issue",
    "powers on only",
    "unable to test",
)

CUSTOM_SHOP_POLLUTION_KEYWORDS = (
    "custom shop",
    "murphy lab",
    "murphy",
    "historic",
    "true historic",
    "reissue",
    "vos",
    "collector's choice",
    "collectors choice",
    "brazilian",
    "stinger",
    "masterbuilt",
    "master built",
    "team built",
    "heavy relic",
    "journeyman",
    "time machine",
    "cunetto",
    "private stock",
    "wood library",
    "artist package",
    "golden era",
    "marquis",
    "pre-war",
    "signed",
    "autographed",
    "prototype",
)

HISTORIC_OR_VINTAGE_PATTERN = re.compile(
    r"\b(r[467890]|19[3-7]\d|'5[246789]|'6[0-58]|57\s+goldtop|58\s+les\s+paul|59\s+les\s+paul)\b",
    re.IGNORECASE,
)


def _is_custom_shop_or_vintage_title(text: str) -> bool:
    lower = text.lower()
    lower_clean = re.sub(r"\b(1960\s+classic|classic\s+1960|standard\s+[56]0s|[56]0s\s+standard)\b", " ", lower)
    if any(kw in lower_clean for kw in CUSTOM_SHOP_POLLUTION_KEYWORDS):
        return True
    if HISTORIC_OR_VINTAGE_PATTERN.search(lower_clean):
        return True
    return False


@dataclass
class LiveGuitarListing:
    listing_id: str
    platform: str
    title: str
    canonical_model: str
    condition: str
    seller_name: str
    location: str
    ask_price_usd: float
    shipping_usd: float
    bench_setup_usd: float
    all_in_cost_usd: float
    estimated_comp_usd: float
    platform_fees_usd: float
    estimated_net_profit_usd: float
    net_roi_pct: float
    signal: str
    listing_url: str
    item_category: str = "Guitars"
    recommended_offer_usd: float = 0.0
    profit_at_recommended_offer_usd: float = 0.0
    max_offer_usd: float = 0.0
    break_even_offer_usd: float = 0.0
    image_urls: List[str] = field(default_factory=list)
    description: str = ""
    extra_metadata: Dict[str, Any] = field(default_factory=dict)
    audit_notes: List[str] = field(default_factory=list)


def _is_valid_item_title(title: str, item_category: str = "Guitars") -> bool:
    lower = title.lower()
    if any(bad in lower for bad in COMMON_EXCLUDE_KEYWORDS):
        return False

    if item_category == "Guitars":
        if any(bad in lower for bad in GUITAR_ONLY_EXCLUDE_KEYWORDS):
            return False
        if "case" in lower and not any(
            ok in lower for ok in ("with case", "w/ case", "w/case", "w case", "ohsc", "includes case", "with hard", "w/ hard", "with original")
        ):
            if any(
                ck in lower
                for ck in ("custom case", "les paul case", "strat case", "tele case", "acoustic case", "fitted case", "plush case", "canadian made")
            ) or lower.strip(" !.").endswith("case"):
                return False
    elif item_category == "Guitar Pedals & Effects":
        if any(bad in lower for bad in PEDAL_EXCLUDE_KEYWORDS):
            return False
    elif item_category == "Microphones & Studio Audio":
        if any(bad in lower for bad in MIC_EXCLUDE_KEYWORDS):
            return False
    elif item_category == "Amplifiers & Heads":
        if any(bad in lower for bad in AMP_EXCLUDE_KEYWORDS):
            return False

    return True


def _is_reverb_category_match(item: Dict[str, Any], item_category: str = "Guitars") -> bool:
    """Ensures a Reverb API listing matches the requested gear category."""
    cats = item.get("categories", [])
    if not cats:
        return True
    full_names = " | ".join(str(c.get("full_name", "")).lower() for c in cats if isinstance(c, dict))
    if not full_names:
        return True

    if item_category == "Guitars":
        if any(bad_cat in full_names for bad_cat in ("accessories", "cases", "gig bags", "parts", "pickups", "amps", "amplifiers", "pedals", "merchandise")):
            return False
        return "guitar" in full_names
    elif item_category == "Guitar Pedals & Effects":
        if any(bad_cat in full_names for bad_cat in ("cables", "power supplies", "cases", "merchandise", "parts")):
            return False
        return any(ok in full_names for ok in ("pedal", "effects", "multi-effect", "preamp", "looper", "wah", "overdrive", "distortion", "delay", "reverb", "fuzz"))
    elif item_category == "Microphones & Studio Audio":
        if any(bad_cat in full_names for bad_cat in ("stands", "cables", "cases", "parts", "windscreens", "mounts")):
            return False
        return any(ok in full_names for ok in ("microphone", "pro audio", "vocal", "condenser", "dynamic", "ribbon", "preamp", "interface"))
    elif item_category == "Amplifiers & Heads":
        if any(bad_cat in full_names for bad_cat in ("covers", "cases", "parts", "tubes", "footswitch", "cables", "attenuator")):
            return False
        return any(ok in full_names for ok in ("amp", "combos", "heads", "cabinets"))

    return True


def _strip_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    cleaned = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    lines = [" ".join(line.split()) for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line)


# ==============================================================================
# SPECIFIC MODEL SIGNATURE EXTRACTOR & LIVE REVERB EXACT-COMP ENGINE
# ==============================================================================

_COMP_CACHE: Dict[str, Tuple[float, str, int, int]] = {}


def extract_specific_model_query(
    title: str,
    make_hint: str = "",
    model_hint: str = "",
    item_category: str = "Guitars",
) -> str:
    """
    Extracts the specific brand + exact model code/sub-series from a raw listing title
    across Guitars, Pedals, Microphones, and Amplifiers.
    """
    if make_hint and model_hint and len(model_hint.strip()) >= 2:
        combined = f"{make_hint.strip()} {model_hint.strip()}"
        combined = re.sub(r"\([^)]*\)|#[A-Za-z0-9\-]+", " ", combined)
        combined = " ".join(combined.split())
        if 2 <= len(combined.split()) <= 6:
            return combined

    cleaned = re.sub(r"\b(sn|s/n|serial|item|model)\s*[:#]?\s*[a-z0-9\-]+\b", " ", title, flags=re.IGNORECASE)
    cleaned = re.sub(r"\([^)]*\)|\[[^\]]*\]|#[A-Za-z0-9\-]+", " ", cleaned)
    cleaned = re.sub(r"\b(19[5-9]\d|20[0-2]\d)\b", " ", cleaned)

    allowed_numbers = {
        "335", "339", "175", "100", "18", "28", "15", "24", "550", "450", "350", "50", "60",
        "57", "58", "7", "20", "421", "414", "214", "102", "103", "2020", "4040", "87",
        "9", "808", "2", "3", "5", "6", "1", "30", "40", "65", "800", "900",
    }

    tokens = re.findall(r"[A-Za-z0-9'\-]+", cleaned)
    kept: List[str] = []
    for tok in tokens:
        low = tok.lower().strip("-'")
        if not low:
            continue
        if len(low) == 1 and not low.isdigit():
            continue
        if low in NOISE_WORDS:
            continue
        if low.isdigit() and low not in allowed_numbers:
            continue
        if low not in [k.lower() for k in kept]:
            kept.append(tok)
        if len(kept) >= 5:
            break

    result = " ".join(kept) if len(kept) >= 2 else title[:45].strip()
    res_low = result.lower()

    if item_category == "Guitars":
        if "les paul" in res_low and not any(b in res_low for b in ("gibson", "epiphone", "chibson", "replica", "maestro")):
            result = f"Gibson {result}"
        elif ("stratocaster" in res_low or "telecaster" in res_low) and not any(b in res_low for b in ("fender", "squier", "squire", "starcaster")):
            result = f"Fender {result}"
    return result


def _has_specific_model_token(specific_model_query: str) -> bool:
    tokens = [t.lower().strip("-'") for t in specific_model_query.split()]
    non_generic = [t for t in tokens if t and t not in GENERIC_QUERY_WORDS]
    return len(non_generic) >= 1


def normalize_condition_tier(cond_text: str) -> str:
    """Normalizes raw condition strings into standard used market tiers."""
    c = cond_text.lower()
    if "mint" in c or "like new" in c:
        return "Mint"
    if "excellent" in c or "near mint" in c:
        return "Excellent"
    if "very good" in c or "vg" in c:
        return "Very Good"
    if "fair" in c or "poor" in c or "for parts" in c:
        return "Fair"
    if "good" in c or "used" in c or "thrift" in c or "uninspected" in c or "player" in c:
        return "Good"
    return "Very Good"


def lookup_live_reverb_comp_for_model(
    specific_model_query: str,
    source_title: str = "",
    target_condition: str = "Used",
    exclude_listing_id: str = "",
    item_category: str = "Guitars",
) -> Tuple[float, str, int, int]:
    """
    Queries Reverb's live listings for the exact extracted model signature and calculates
    the actual median resale comp based on genuine used condition (strictly excluding Brand New).
    Returns: (condition_resale_comp, condition_matched_label, comp_count, excluded_count)
    """
    ref_text = f"{source_title} {specific_model_query}".strip()
    _, heuristic_val = _heuristic_tier_comp(ref_text, item_category=item_category)

    if not _has_specific_model_token(specific_model_query):
        return (heuristic_val, "Category / Sub-Model Baseline", 0, 0)

    source_is_custom_or_vintage = _is_custom_shop_or_vintage_title(ref_text)
    target_tier = normalize_condition_tier(target_condition)
    cache_key = f"{item_category}::{specific_model_query.lower().strip()}::cs={int(source_is_custom_or_vintage)}::cond={target_tier}"
    if cache_key in _COMP_CACHE:
        return _COMP_CACHE[cache_key]

    headers = {
        "Accept-Version": "3.0",
        "Accept": "application/hal+json",
        "User-Agent": "GuitarEtl-ExactCompEngine/2.3",
    }
    encoded = urllib.parse.quote(specific_model_query)
    url = f"https://api.reverb.com/api/listings/all?query={encoded}&condition=used&per_page=35"

    min_comp_price = CATEGORY_CATALOG.get(item_category, CATEGORY_CATALOG["Guitars"])["min_price_usd"]
    polluted_excluded = 0

    try:
        r = requests.get(url, headers=headers, timeout=6)
        if r.status_code == 200:
            listings = r.json().get("listings", [])
            query_tokens = [
                t.lower()
                for t in re.findall(r"[A-Za-z0-9]+", specific_model_query)
                if len(t) >= 2 and t.lower() not in {"guitar", "pedal", "microphone", "amp", "used", "by", "the"}
            ]
            ref_low = ref_text.lower()
            matched_prices_with_tier: List[Tuple[str, float]] = []

            for item in listings:
                item_id = str(item.get("id", ""))
                if exclude_listing_id and item_id == exclude_listing_id.replace("REV-", ""):
                    continue
                if not _is_reverb_category_match(item, item_category=item_category):
                    continue

                # 1. Strictly exclude Brand New items from used comp calculation
                cond_obj = item.get("condition") or {}
                cond_slug = str(cond_obj.get("slug") or "").lower()
                cond_display = str(cond_obj.get("display_name") or "").lower()
                if "brand-new" in cond_slug or cond_slug == "new" or "brand new" in cond_display or cond_display == "new":
                    polluted_excluded += 1
                    continue

                item_title = item.get("title", "")
                if not _is_valid_item_title(item_title, item_category=item_category):
                    continue
                title_low = item_title.lower()

                # 2. Prevent Custom Shop / Murphy Lab / Historic / Reissue / VOS / Vintage pollution
                if not source_is_custom_or_vintage and _is_custom_shop_or_vintage_title(item_title):
                    polluted_excluded += 1
                    continue

                # 3. Prevent sub-brand cross-pollution
                if ("squier" in ref_low or "squire" in ref_low) != ("squier" in title_low or "squire" in title_low):
                    continue
                if ("epiphone" in ref_low) != ("epiphone" in title_low):
                    continue
                if "prs" in ref_low and ((" se " in f" {ref_low} ") != (" se " in f" {title_low} ")):
                    continue

                # 4. Require token overlap with extracted model signature
                if query_tokens:
                    req_matches = min(2 if item_category != "Guitars" else 3, len(query_tokens))
                    matches = sum(1 for qt in query_tokens[:4] if qt in title_low)
                    if matches < req_matches:
                        continue

                p_str = item.get("price", {}).get("amount")
                if p_str:
                    try:
                        p_val = float(p_str)
                        if p_val >= min_comp_price:
                            if not source_is_custom_or_vintage and heuristic_val >= 50.0 and p_val > heuristic_val * 1.55:
                                polluted_excluded += 1
                                continue
                            item_tier = normalize_condition_tier(cond_display or cond_slug)
                            matched_prices_with_tier.append((item_tier, p_val))
                    except ValueError:
                        pass

            if matched_prices_with_tier:
                tier_prices = [p for tier, p in matched_prices_with_tier if tier == target_tier]
                condition_label = f"Matched {target_tier} Condition"

                if len(tier_prices) < 2:
                    if target_tier in ("Mint", "Excellent"):
                        tier_prices = [p for tier, p in matched_prices_with_tier if tier in ("Mint", "Excellent")]
                        condition_label = "Mint / Excellent Condition"
                    elif target_tier in ("Very Good", "Good"):
                        tier_prices = [p for tier, p in matched_prices_with_tier if tier in ("Very Good", "Good")]
                        condition_label = "Very Good / Good Condition"
                    elif target_tier == "Fair":
                        tier_prices = [p for tier, p in matched_prices_with_tier if tier in ("Fair", "Good")]
                        condition_label = "Fair / Good Condition"

                if len(tier_prices) < 2:
                    tier_prices = [p for _, p in matched_prices_with_tier]
                    condition_label = "Overall Used Market Median"

                if len(tier_prices) >= 2:
                    raw_med = statistics.median(tier_prices)
                    core_prices = [p for p in tier_prices if 0.50 * raw_med <= p <= 1.55 * raw_med]
                    if not core_prices:
                        core_prices = tier_prices
                    used_condition_comp = round(statistics.median(core_prices), 2)

                    res = (used_condition_comp, condition_label, len(core_prices), polluted_excluded)
                    _COMP_CACHE[cache_key] = res
                    return res
    except Exception:
        pass

    res = (heuristic_val, "Standard Used Baseline", 0, polluted_excluded)
    _COMP_CACHE[cache_key] = res
    return res


def _heuristic_tier_comp(title: str, item_category: str = "Guitars") -> Tuple[str, float]:
    lower = title.lower()
    compact = re.sub(r"[\-\s]+", "", lower)

    # ==========================================================================
    # CATEGORY 2: GUITAR PEDALS & EFFECTS
    # ==========================================================================
    if item_category == "Guitar Pedals & Effects":
        if "chase bliss" in lower:
            return ("Chase Bliss Boutique Pedal", 340.00)
        if "strymon" in lower:
            if any(k in lower for k in ("bigsky", "big sky", "timeline", "mobius", "volante", "nightsky", "iridium")):
                return ("Strymon Flagship Workstation Pedal", 335.00)
            return ("Strymon Compact DSP Pedal", 225.00)
        if "eventide" in lower:
            if "h90" in lower:
                return ("Eventide H90 Harmonizer", 695.00)
            if "h9" in lower:
                return ("Eventide H9 Multi-Effects", 320.00)
            return ("Eventide Factor / Stompbox", 215.00)
        if "line 6" in lower or "line6" in lower:
            if "helix" in lower:
                return ("Line 6 Helix Floor / LT", 795.00)
            if "hx stomp" in lower:
                return ("Line 6 HX Stomp", 475.00)
            if "dl4" in lower or "hx effects" in lower or "pod go" in lower:
                return ("Line 6 DL4 / HX / POD Series", 225.00)
            return ("Line 6 Effects Pedal", 95.00)
        if "jhs" in lower:
            if "3 series" in lower:
                return ("JHS 3 Series Pedal", 72.00)
            if "colour box" in lower or "sweet tea" in lower or "double barrel" in lower:
                return ("JHS Dual / Preamp Pedal", 245.00)
            return ("JHS Boutique Effects Pedal", 145.00)
        if "walrus" in lower or "earthquaker" in lower or "eqd" in lower:
            return ("Walrus Audio / EarthQuaker Boutique Pedal", 145.00)
        if "wampler" in lower or "keeley" in lower:
            return ("Wampler / Keeley Boutique Pedal", 125.00)
        if "boss" in lower:
            if "waza" in lower or "-2w" in lower or "-1w" in lower or "dm-2w" in lower or "bd-2w" in lower or "sd-1w" in lower:
                return ("Boss Waza Craft Series Pedal", 130.00)
            if any(k in lower for k in ("dd-500", "rv-500", "md-500", "rc-500", "gt-1000", "gx-100", "sy-300", "rc-600")):
                return ("Boss 500/1000 Workstation / Looper", 265.00)
            if any(k in lower for k in ("dd-200", "rv-200", "ir-200", "eq-200", "od-200", "rc-5", "rv-6", "dd-8", "dd-7", "re-2")):
                return ("Boss Compact Digital Delay/Reverb/Looper", 120.00)
            if any(k in lower for k in ("ds-1", "sd-1", "cs-3", "tu-2", "tu-3", "ch-1", "mt-2")):
                return ("Boss Standard Compact Pedal", 62.00)
            return ("Boss Compact Effects Pedal", 88.00)
        if "ibanez" in lower:
            if "ts808" in lower or "808" in lower:
                return ("Ibanez TS808 Tube Screamer", 125.00)
            if "ts9" in lower or "tube screamer" in lower:
                return ("Ibanez TS9 Tube Screamer", 85.00)
            return ("Ibanez Effects Pedal", 75.00)
        if "electro-harmonix" in lower or "ehx" in lower or "big muff" in lower:
            if "p9" in lower or "pog" in lower or "9 series" in lower or "mel9" in lower or "synth9" in lower or "B9" in lower:
                return ("EHX POG / 9-Series Polyphonic Pedal", 165.00)
            return ("Electro-Harmonix (EHX) Effects Pedal", 78.00)
        if "mxr" in lower or "dunlop" in lower or "cry baby" in lower or "crybaby" in lower or "proco" in lower or "rat " in lower:
            if "ten band" in lower or "10 band" in lower or "carbon copy" in lower or "timmy" in lower or "duke of tone" in lower:
                return ("MXR Analog Delay / Boutique Collaboration", 105.00)
            return ("MXR / Dunlop / ProCo Standard Pedal", 72.00)
        if "tc electronic" in lower or "digitech" in lower:
            return ("TC Electronic / DigiTech Pedal", 75.00)
        return ("Used Guitar Effects Pedal", 85.00)

    # ==========================================================================
    # CATEGORY 3: MICROPHONES & STUDIO AUDIO
    # ==========================================================================
    if item_category == "Microphones & Studio Audio":
        if "neumann" in lower:
            if "u87" in lower or "u 87" in lower:
                return ("Neumann U87 Studio Condenser", 2450.00)
            if "tlm 103" in lower or "tlm103" in lower or "km 184" in lower or "km184" in lower:
                return ("Neumann TLM 103 / KM 184 Studio Mic", 795.00)
            if "tlm 102" in lower or "tlm102" in lower:
                return ("Neumann TLM 102 Studio Condenser", 525.00)
            return ("Neumann Studio Microphone", 650.00)
        if "shure" in lower:
            if "sm7b" in lower or "sm7db" in lower or "sm 7b" in lower:
                return ("Shure SM7B / SM7dB Broadcast Dynamic Mic", 285.00)
            if "ksm" in lower:
                return ("Shure KSM Studio Condenser / Dynamic", 425.00)
            if "beta 52" in lower or "beta 58" in lower or "beta 57" in lower or "beta 87" in lower or "super 55" in lower:
                return ("Shure Beta / Super 55 Series Mic", 125.00)
            if "sm57" in lower or "sm58" in lower or "sm 57" in lower or "sm 58" in lower:
                return ("Shure SM57 / SM58 Industry Standard Dynamic", 78.00)
            if "mv7" in lower:
                return ("Shure MV7 Podcast Dynamic Mic", 155.00)
            return ("Shure Professional Microphone", 95.00)
        if "electro-voice" in lower or "electro voice" in lower or "re20" in lower or "re-20" in lower:
            if "re20" in lower or "re-20" in lower or "re27" in lower:
                return ("Electro-Voice RE20 / RE27 Broadcast Mic", 335.00)
            return ("Electro-Voice Dynamic Microphone", 88.00)
        if "sennheiser" in lower:
            if "md 421" in lower or "md421" in lower or "md 441" in lower or "mkh 416" in lower or "mkh416" in lower:
                return ("Sennheiser MD421 / MKH416 Pro Studio Mic", 315.00)
            if "e906" in lower or "e935" in lower or "e945" in lower or "mk4" in lower:
                return ("Sennheiser e900 / MK4 Series Microphone", 145.00)
            return ("Sennheiser e835 / Dynamic Microphone", 75.00)
        if "akg" in lower:
            if "c414" in lower or "c 414" in lower:
                return ("AKG C414 Multi-Pattern Condenser", 695.00)
            if "c214" in lower or "c 214" in lower or "d112" in lower:
                return ("AKG C214 / D112 Studio Microphone", 245.00)
            return ("AKG Studio Condenser Microphone", 95.00)
        if "audio-technica" in lower or "audio technica" in lower:
            if "at4050" in lower or "at4040" in lower or "at4033" in lower or "bp40" in lower:
                return ("Audio-Technica 40-Series Pro Condenser", 235.00)
            return ("Audio-Technica AT2020 / AT2035 Condenser", 78.00)
        if "warm audio" in lower:
            return ("Warm Audio Boutique Recreation Mic", 395.00)
        if "rode" in lower:
            if "nt1" in lower or "nt2" in lower or "procaster" in lower or "podmic usb" in lower:
                return ("Rode NT1 / Procaster Studio Mic", 155.00)
            return ("Rode Studio / Broadcast Microphone", 85.00)
        if "blue" in lower:
            if "baby bottle" in lower or "bluebird" in lower:
                return ("Blue Bluebird / Baby Bottle XLR Condenser", 195.00)
            return ("Blue Condenser Microphone", 75.00)
        return ("Used Studio / Vocal Microphone", 95.00)

    # ==========================================================================
    # CATEGORY 4: AMPLIFIERS & HEADS
    # ==========================================================================
    if item_category == "Amplifiers & Heads":
        if "mesa" in lower or "boogie" in lower:
            return ("Mesa Boogie Tube Amplifier (USA)", 1150.00)
        if "fender" in lower:
            if any(k in lower for k in ("twin reverb", "deluxe reverb", "princeton reverb", "vibrolux", "super-sonic", "bassman")):
                return ("Fender Vintage Reissue / Tube Reverb Amp", 895.00)
            if any(k in lower for k in ("blues junior", "blues deluxe", "hot rod deluxe", "hot rod deville", "pro junior")):
                return ("Fender Blues Jr / Hot Rod Tube Combo", 465.00)
            if any(k in lower for k in ("tone master", "tonemaster")):
                return ("Fender Tone Master Series Amp", 675.00)
            if any(k in lower for k in ("mustang", "champion", "frontman", "rumble")):
                return ("Fender Solid-State / Modeling Combo", 135.00)
            return ("Fender Guitar Amplifier", 325.00)
        if "marshall" in lower:
            if any(k in lower for k in ("jcm800", "jcm 800", "jcm900", "jcm 900", "jvm", "plex", "1959", "silver jubilee")):
                return ("Marshall UK Tube Head / Combo", 1150.00)
            if any(k in lower for k in ("dsl40", "dsl20", "origin", "studio")):
                return ("Marshall DSL / Origin Tube Series", 475.00)
            if "mg" in lower or "code" in lower:
                return ("Marshall MG / Code Practice Amp", 120.00)
            return ("Marshall Guitar Amplifier", 395.00)
        if "vox" in lower:
            if "ac30" in lower or "ac15" in lower:
                return ("Vox AC15 / AC30 Tube Combo", 545.00)
            return ("Vox Guitar Amplifier", 165.00)
        if "orange" in lower:
            if any(k in lower for k in ("rockerverb", "thunderverb", "ad30", "or15", "rocker")):
                return ("Orange Tube Amplifier", 695.00)
            return ("Orange Crush / Terror Amplifier", 225.00)
        if "boss" in lower or "katana" in lower:
            if "100" in lower or "artist" in lower:
                return ("Boss Katana 100 / Artist Amp", 295.00)
            return ("Boss Katana 50 / Modeling Amp", 185.00)
        return ("Used Guitar Amplifier", 245.00)

    # ==========================================================================
    # CATEGORY 1: GUITARS (ELECTRIC & ACOUSTIC)
    # ==========================================================================
    if any(rk in lower for rk in (
        "prs style", "strat style", "tele style", "les paul style", "lp style",
        "style guitar", "copy guitar", "partscaster", "chibson", "tribute build", "replica",
        "kit build", "diy build", "unbranded", "akusa"
    )):
        return ("Partscaster / DIY Kit / Style Copy", 165.00)

    if any(k in lower for k in ("lxk2", "lx1", "lxm", "little martin")):
        return ("Martin Little Martin Travel Series (LXK2 / LX1)", 350.00)
    if any(k in lower for k in ("djr", "dreadnought junior", "000jr", "000cjr")):
        return ("Martin Junior Series (DJr / 000Jr)", 450.00)
    if any(k in compact for k in ("dx1", "dx2", "dxmae", "xseries", "00x2", "000x2", "gpcx")):
        return ("Martin X Series HPL", 475.00)
    if any(k in compact for k in ("d10e", "d12e", "d13e", "00010e", "00012e", "roadseries", "drs1", "drs2")):
        return ("Martin Road Series", 795.00)
    if any(k in compact for k in ("d15", "00015", "0015")):
        return ("Martin 15 Series Solid Mahogany (USA)", 1150.00)
    if any(k in compact for k in ("d18", "00018", "om18")):
        return ("Martin Standard 18 Series (USA)", 2150.00)
    if any(k in compact for k in ("d28", "hd28", "00028", "om28")):
        return ("Martin Standard 28 Series (USA)", 2450.00)
    if "sigma" in lower:
        return ("Sigma by Martin Acoustic", 325.00)

    if "taylor" in lower:
        if "baby" in lower or "bt1" in lower or "bt2" in lower or "big baby" in lower:
            return ("Taylor Baby / Big Baby Travel Series", 320.00)
        if "gs mini" in lower:
            return ("Taylor GS Mini Series", 445.00)
        if "academy" in lower or "110" in lower or "114" in lower:
            return ("Taylor 100 / Academy Series", 575.00)
        if "210" in lower or "214" in lower:
            return ("Taylor 200 Series", 795.00)
        if any(k in lower for k in ("314", "414", "514", "714", "814")):
            return ("Taylor USA 300-800 Series", 1650.00)
        return ("Taylor Acoustic Guitar", 595.00)

    if "gretsch" in lower:
        if "streamliner" in lower or "g24" in lower or "g26" in lower or "g22" in lower or "jim dandy" in lower:
            return ("Gretsch Streamliner / Roots Series", 345.00)
        if "electromatic" in lower or "g54" in lower or "g52" in lower or "g56" in lower:
            return ("Gretsch Electromatic Series", 565.00)
        if "professional" in lower or "japan" in lower or "g61" in lower or "falcon" in lower or "setzer" in lower:
            return ("Gretsch Professional MIJ Series", 1850.00)
        return ("Gretsch Electromatic / Hollowbody", 525.00)

    if "starcaster" in lower:
        return ("Starcaster by Fender Electric", 135.00)
    if "squier" in lower or "squire" in lower:
        if "classic vibe" in lower or "40th" in lower:
            return ("Squier Classic Vibe Series", 340.00)
        if "affinity" in lower:
            return ("Squier Affinity Series", 155.00)
        if "bullet" in lower or "sonic" in lower or "debut" in lower:
            return ("Squier Bullet / Sonic Series", 115.00)
        return ("Squier by Fender Electric", 150.00)

    if "epiphone" in lower:
        if any(k in lower for k in ("special", "sl", "junior", "jr", "dr-100", "pro-1", "les paul 100", "lp-100", "lp100", "express")):
            return ("Epiphone Entry / Special / LP-100 Series", 145.00)
        if "tribute" in lower or "studio" in lower:
            return ("Epiphone Studio / Tribute Series", 245.00)
        if "1959" in lower or "inspired by gibson" in lower or "ibgc" in lower or "custom" in lower or "casino" in lower or "sheraton" in lower:
            return ("Epiphone Inspired by Gibson / Custom / Archtop", 575.00)
        return ("Epiphone Standard Series", 385.00)

    is_gibson_family = "gibson" in lower or (
        ("les paul" in lower or "sg standard" in lower)
        and not any(x in lower for x in ("epiphone", "chibson", "replica", "clone", "copy", "maestro"))
    )
    if is_gibson_family:
        if "les paul custom" in lower:
            return ("Gibson Les Paul Custom (USA)", 3350.00)
        if "les paul standard" in lower or "standard 50s" in lower or "standard 60s" in lower:
            return ("Gibson Les Paul Standard (USA)", 2150.00)
        if "traditional" in lower:
            return ("Gibson Les Paul Traditional (USA)", 1895.00)
        if "classic" in lower:
            return ("Gibson Les Paul Classic (USA)", 1750.00)
        if "junior" in lower or "les paul special" in lower:
            return ("Gibson Les Paul Junior / Special (USA)", 1250.00)
        if "studio" in lower or "tribute" in lower or "faded" in lower:
            return ("Gibson Les Paul Studio / Tribute (USA)", 995.00)
        if "sg standard" in lower:
            return ("Gibson SG Standard (USA)", 1395.00)
        return ("Gibson USA Electric", 1450.00)

    is_fender_family = "fender" in lower or (
        ("stratocaster" in lower or "telecaster" in lower)
        and not any(x in lower for x in ("squier", "squire", "starcaster", "partscaster", "replica"))
    )
    if is_fender_family:
        if "american professional" in lower or "american pro" in lower or "american standard" in lower or "american performer" in lower or "american ultra" in lower:
            return ("Fender American Pro / Standard (USA)", 1250.00)
        if "japan" in lower or "mij" in lower or "cij" in lower:
            return ("Fender MIJ / Japan Series", 950.00)
        if "player" in lower or "mexico" in lower or "mim" in lower or "standard" in lower:
            return ("Fender Player / Standard (MIM)", 565.00)
        return ("Fender Standard Series", 495.00)

    if "prs" in lower or "paul reed smith" in lower:
        if any(ak in lower for ak in ("acoustic", "angelus", "tonare", "parlor", "p20", "p50", "a20", "a40", "t40", "a50", "t50", "a60", "t60")):
            return ("PRS SE Acoustic Series (Import)", 425.00)
        if any(sk in lower for sk in ("se ", " se", "se-", "se/", "student edition", "indonesia", "korea", "cor-tek", "cortek")):
            return ("PRS SE Series (Import)", 525.00)
        if "s2" in lower or "ce 24" in lower or "ce24" in lower or "bolt-on" in lower or "bolt on" in lower:
            return ("PRS S2 / CE Series (USA)", 1295.00)
        if any(uk in lower for uk in ("core", "usa", "made in usa", "maryland", "custom 24", "custom 22", "mccarty", "594", "10-top", "10 top", "private stock")):
            return ("PRS Core Series (USA)", 2750.00)
        return ("PRS SE Series (Import)", 525.00)

    if "ibanez" in lower:
        if "gio" in lower or "grg" in lower or "grx" in lower:
            return ("Ibanez GIO Series", 140.00)
        if "prestige" in lower or "genesis" in lower or "rg550" in lower or "japan" in lower:
            return ("Ibanez MIJ Prestige / Genesis", 850.00)
        return ("Ibanez Standard Series", 350.00)

    if "yamaha" in lower:
        if "fg" in lower or "fs" in lower or "apx" in lower or "pacifica" in lower:
            return ("Yamaha FG / Pacifica Series", 225.00)
        return ("Yamaha Guitar", 275.00)

    return ("Used Acoustic / Electric Guitar", 325.00)


# ==============================================================================
# OFFER PRICE & MAXIMUM AUCTION BID CALCULATOR
# ==============================================================================

def calculate_offer_recommendations(
    estimated_comp_usd: float,
    platform_fees_usd: float,
    shipping_usd: float,
    bench_setup_usd: float,
    item_category: str = "Guitars",
) -> Tuple[float, float, float, float]:
    """
    Computes actionable negotiation and auction bidding targets for any item
    (whether currently profitable at the seller's ask price or not):
      - break_even_offer_usd: 0% Net ROI (Net Resale Proceeds - Shipping - Setup/Test)
      - recommended_offer_usd: Target offer for ~25% Net ROI (and category min dollar profit)
      - profit_at_recommended_offer_usd: Expected Net Profit when bought at recommended_offer_usd
      - max_offer_usd: Suggested Maximum Offer / Max Auction Bid Ceiling (~12% Net ROI floor)
    """
    cat_cfg = CATEGORY_CATALOG.get(item_category, CATEGORY_CATALOG["Guitars"])
    target_min_profit = float(cat_cfg["target_min_profit_usd"])
    floor_min_profit = float(cat_cfg["floor_min_profit_usd"])

    net_resale_proceeds = max(0.0, estimated_comp_usd - platform_fees_usd)
    fixed_inbound_costs = shipping_usd + bench_setup_usd

    # 1. Break-even offer/bid price
    break_even_offer = max(5.0, round(net_resale_proceeds - fixed_inbound_costs, 2))

    # 2. Recommended Target Offer (~25% Net ROI + minimum dollar profit cushion)
    # AllInCost_target = net_resale_proceeds / 1.25 -> Offer = AllInCost_target - fixed_inbound_costs
    rec_by_roi = (net_resale_proceeds / 1.25) - fixed_inbound_costs
    rec_by_dollar = net_resale_proceeds - fixed_inbound_costs - target_min_profit
    recommended_offer = max(5.0, round(min(rec_by_roi, rec_by_dollar), 2))

    # 3. Suggested Maximum Offer / Max Auction Bid (~12% Net ROI floor + floor dollar profit)
    max_by_roi = (net_resale_proceeds / 1.12) - fixed_inbound_costs
    max_by_dollar = net_resale_proceeds - fixed_inbound_costs - floor_min_profit
    max_offer = max(recommended_offer, round(min(max_by_roi, max_by_dollar), 2))

    # 4. Expected Net Profit if acquired at recommended_offer
    profit_at_rec = round(net_resale_proceeds - (recommended_offer + fixed_inbound_costs), 2)

    return (recommended_offer, profit_at_rec, max_offer, break_even_offer)


# ==============================================================================
# POST AUTHENTICITY, CONDITION & RISK INVESTIGATOR
# ==============================================================================

def investigate_and_score_listing(
    listing_id: str,
    platform: str,
    title: str,
    condition: str,
    seller_name: str,
    location: str,
    ask_price_usd: float,
    shipping_usd: float,
    listing_url: str,
    image_urls: List[str],
    description: str,
    make_hint: str = "",
    model_hint: str = "",
    item_category: str = "Guitars",
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Optional[LiveGuitarListing]:
    combined_text = f"{title} {description}".lower()
    audit_notes: List[str] = []
    cat_cfg = CATEGORY_CATALOG.get(item_category, CATEGORY_CATALOG["Guitars"])

    specific_model_query = extract_specific_model_query(
        title, make_hint, model_hint, item_category=item_category
    )
    tier_label, heuristic_comp = _heuristic_tier_comp(
        f"{title} {description}", item_category=item_category
    )
    used_comp, condition_label, comp_count, polluted_excluded = lookup_live_reverb_comp_for_model(
        specific_model_query,
        source_title=f"{title} {description}",
        target_condition=condition,
        exclude_listing_id=listing_id,
        item_category=item_category,
    )

    if polluted_excluded > 0:
        audit_notes.append(
            f"[Data Guard] Excluded {polluted_excluded} Brand New / Custom Shop / Vintage / Outlier "
            f"listings from '{specific_model_query}' used comp pool."
        )

    if comp_count >= 2:
        estimated_comp = used_comp
        canonical_label = f"{specific_model_query} ({comp_count} Used Comps)"
        audit_notes.append(
            f"[Used Condition Comp] Evaluated genuine used '{specific_model_query}' listings (Brand New strictly excluded). "
            f"{condition_label} -> Resale Comp: ${used_comp:,.2f}."
        )
    else:
        estimated_comp = heuristic_comp
        canonical_label = tier_label
        audit_notes.append(
            f"[Sub-Model Tier Match] Classified as '{tier_label}' (Standard Used Comp: ${heuristic_comp:,.2f})."
        )

    # Check for Replica / Partscaster / Counterfeit claims
    is_replica_or_partscaster = any(rk in combined_text for rk in REPLICA_KEYWORDS)
    claims_high_end = any(
        hk in combined_text for hk in ("custom shop", "masterbuilt", "david gilmour", "1959 reissue", "murphy lab")
    )

    if is_replica_or_partscaster or (item_category == "Guitars" and claims_high_end and ask_price_usd < 1100.0):
        capped_comp = min(estimated_comp, max(ask_price_usd * 1.05, 195.00 if item_category == "Guitars" else 65.00))
        audit_notes.append(
            f"[Authenticity Warning] Flagged as likely Partscaster / DIY Kit / Clone (resale comp capped at ${capped_comp:,.2f})."
        )
        estimated_comp = round(capped_comp, 2)
        canonical_label = f"{specific_model_query} [Clone / Unverified]"

    # Category-specific Setup / Bench Test Reserve
    bench_setup_usd = float(cat_cfg["bench_setup_usd"])
    has_repair_risk = any(rk in combined_text for rk in REPAIR_RISK_KEYWORDS)
    if has_repair_risk or "Goodwill" in platform:
        bench_setup_usd = float(cat_cfg["untested_setup_usd"])
        estimated_comp = round(estimated_comp * 0.92, 2)
        audit_notes.append(
            f"[Condition Reserve] Thrift auction / untested status: applied ${bench_setup_usd:,.2f} bench reserve and 8% condition haircut."
        )
    else:
        audit_notes.append(f"[Prep Allowance] Applied ${bench_setup_usd:,.2f} {item_category.lower()} prep/test allowance.")

    all_in_cost = round(ask_price_usd + shipping_usd + bench_setup_usd, 2)
    platform_fees = round(estimated_comp * REVERB_FEE_RATE + REVERB_FIXED_FEE_USD, 2)
    net_profit = round(estimated_comp - platform_fees - all_in_cost, 2)
    net_roi_pct = round((net_profit / all_in_cost) * 100.0, 2) if all_in_cost > 0 else 0.0

    # Calculate Recommended Offer & Max Offer / Auction Bid Ceiling
    rec_offer, profit_at_rec, max_offer, break_even_offer = calculate_offer_recommendations(
        estimated_comp_usd=estimated_comp,
        platform_fees_usd=platform_fees,
        shipping_usd=shipping_usd,
        bench_setup_usd=bench_setup_usd,
        item_category=item_category,
    )
    audit_notes.append(
        f"[Offer & Bid Guidance] Recommended Offer: ${rec_offer:,.2f} (locks in +${profit_at_rec:,.2f} net profit / ~25% ROI) | "
        f"Max Offer / Bid Ceiling: ${max_offer:,.2f} (~12% ROI floor) | Break-Even Price: ${break_even_offer:,.2f}."
    )

    if "Clone / Unverified" in canonical_label:
        signal = "PASS (REPLICA/PARTS)"
    elif net_roi_pct > 160.0 and "Goodwill" not in platform:
        audit_notes.append("[Verify Serial] High spread (>160% ROI) on classified post — verify serial & photos before purchase.")
        signal = "VERIFY_AUTHENTICITY"
    elif net_roi_pct >= 15.0 and net_profit >= float(cat_cfg["floor_min_profit_usd"]):
        signal = "STRONG_BUY"
    elif net_roi_pct >= 5.0 and net_profit > 0:
        signal = "HOLD"
    elif ask_price_usd <= max_offer * 1.20:
        signal = "MAKE_OFFER"
    else:
        signal = "PASS (OFFER ONLY)"

    meta = dict(extra_metadata or {})
    meta["Category"] = item_category
    meta["Extracted Model Signature"] = specific_model_query
    meta["Recommended Offer (25% ROI)"] = f"${rec_offer:,.2f} (Est. Net Profit: +${profit_at_rec:,.2f})"
    meta["Suggested Max Offer / Bid (12% ROI)"] = f"${max_offer:,.2f}"
    meta["Break-Even Price"] = f"${break_even_offer:,.2f}"
    if comp_count >= 2:
        meta["Reverb Used Comps"] = f"{comp_count} matched ({condition_label} -> Used Comp ${used_comp:,.2f})"

    return LiveGuitarListing(
        listing_id=listing_id,
        platform=platform,
        title=title,
        canonical_model=canonical_label,
        condition=condition,
        seller_name=seller_name,
        location=location,
        ask_price_usd=round(ask_price_usd, 2),
        shipping_usd=round(shipping_usd, 2),
        bench_setup_usd=round(bench_setup_usd, 2),
        all_in_cost_usd=all_in_cost,
        estimated_comp_usd=round(estimated_comp, 2),
        platform_fees_usd=platform_fees,
        estimated_net_profit_usd=net_profit,
        net_roi_pct=net_roi_pct,
        signal=signal,
        listing_url=listing_url,
        item_category=item_category,
        recommended_offer_usd=rec_offer,
        profit_at_recommended_offer_usd=profit_at_rec,
        max_offer_usd=max_offer,
        break_even_offer_usd=break_even_offer,
        image_urls=image_urls,
        description=description,
        extra_metadata=meta,
        audit_notes=audit_notes,
    )


# ==============================================================================
# DEDUPLICATION GATE (Title Fingerprint + Any-Shared-Photo-Hash Detection)
# ==============================================================================

def deduplicate_listings(listings: List[LiveGuitarListing]) -> Tuple[List[LiveGuitarListing], int]:
    unique: List[LiveGuitarListing] = []
    seen_title_keys: Set[str] = set()
    seen_image_hashes: Set[str] = set()
    removed_count = 0

    for item in listings:
        norm_title = re.sub(r"[^a-z0-9]", "", item.title.lower())[:38]
        title_key = f"{norm_title}_{int(item.ask_price_usd)}"
        if title_key in seen_title_keys:
            removed_count += 1
            continue

        item_img_keys: Set[str] = set()
        for url in item.image_urls:
            fname = url.split("/")[-1].split("?")[0]
            if fname:
                item_img_keys.add(fname)

        if item_img_keys and item_img_keys.intersection(seen_image_hashes):
            removed_count += 1
            continue

        seen_title_keys.add(title_key)
        seen_image_hashes.update(item_img_keys)
        unique.append(item)

    return (unique, removed_count)


# ==============================================================================
# 1. REVERB LIVE MARKETPLACE CONNECTOR
# ==============================================================================

def _fetch_reverb_detail(listing_id: str, headers: Dict[str, str]) -> Dict[str, Any]:
    try:
        r = requests.get(
            f"https://api.reverb.com/api/listings/{listing_id}",
            headers=headers,
            timeout=6,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def fetch_live_reverb_listings(
    query: str,
    max_items: int = 4,
    item_category: str = "Guitars",
) -> Tuple[List[LiveGuitarListing], float]:
    headers = {
        "Accept-Version": "3.0",
        "Accept": "application/hal+json",
        "User-Agent": "GuitarEtl-ArbitrageScanner/2.3",
    }
    encoded_q = urllib.parse.quote(query)
    url = f"https://api.reverb.com/api/listings/all?query={encoded_q}&condition=used&per_page=35"
    cat_cfg = CATEGORY_CATALOG.get(item_category, CATEGORY_CATALOG["Guitars"])
    min_price = float(cat_cfg["min_price_usd"])
    default_ship = float(cat_cfg["default_reverb_ship_usd"])

    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return ([], 350.0)

        raw_listings = resp.json().get("listings", [])
        valid_items = []
        prices = []

        for item in raw_listings:
            if not _is_reverb_category_match(item, item_category=item_category):
                continue
            cond_obj = item.get("condition") or {}
            cond_slug = str(cond_obj.get("slug") or "").lower()
            if "brand-new" in cond_slug or cond_slug == "new":
                continue

            title = item.get("title", "")
            if not _is_valid_item_title(title, item_category=item_category):
                continue
            price_str = item.get("price", {}).get("amount")
            if not price_str:
                continue
            try:
                price_val = float(price_str)
            except ValueError:
                continue
            if price_val < min_price:
                continue
            prices.append(price_val)
            valid_items.append((price_val, item))

        if not valid_items:
            return ([], 350.0)

        live_median_comp = round(statistics.median(prices), 2) if prices else 350.0
        valid_items.sort(key=lambda x: x[0])
        candidates = [it for _, it in valid_items[:max_items]]

        results: List[LiveGuitarListing] = []
        for item in candidates:
            lid = str(item.get("id", ""))
            detail = _fetch_reverb_detail(lid, headers) if lid else {}
            source_obj = detail if detail else item

            title = source_obj.get("title", item.get("title", "Used Music Gear"))
            ask_price = float(item.get("price", {}).get("amount", 0.0))

            ship_usd = default_ship
            rates = source_obj.get("shipping", {}).get("rates", [])
            if rates and isinstance(rates, list):
                rate_amt = rates[0].get("rate", {}).get("amount")
                if rate_amt is not None:
                    try:
                        ship_usd = float(rate_amt)
                    except ValueError:
                        ship_usd = default_ship

            photos: List[str] = []
            for p in source_obj.get("photos", []):
                links = p.get("_links", {})
                img_url = (
                    links.get("full", {}).get("href")
                    or links.get("large_crop", {}).get("href")
                    or links.get("small_crop", {}).get("href")
                )
                if img_url and img_url not in photos:
                    photos.append(img_url)

            cond = source_obj.get("condition", {}).get("display_name", "Used")
            shop_name = source_obj.get("shop_name") or source_obj.get("shop", {}).get("name") or "Reverb Seller"
            locality = source_obj.get("shop", {}).get("locality", "")
            region = source_obj.get("shop", {}).get("region", "")
            loc_str = ", ".join(p for p in [locality, region] if p) or "USA"
            web_url = source_obj.get("_links", {}).get("web", {}).get("href", f"https://reverb.com/item/{lid}")
            desc = _strip_html(source_obj.get("description", ""))
            make_str = str(source_obj.get("make", "") or "")
            model_str = str(source_obj.get("model", "") or "")

            scored = investigate_and_score_listing(
                listing_id=f"REV-{lid}",
                platform="Reverb",
                title=title,
                condition=cond,
                seller_name=shop_name,
                location=loc_str,
                ask_price_usd=ask_price,
                shipping_usd=ship_usd,
                listing_url=web_url,
                image_urls=photos,
                description=desc,
                make_hint=make_str,
                model_hint=model_str,
                item_category=item_category,
                extra_metadata={
                    "Make": make_str,
                    "Model": model_str,
                    "Year": source_obj.get("year", "Unknown"),
                    "Finish": source_obj.get("finish", ""),
                },
            )
            if scored:
                results.append(scored)

        return (results, live_median_comp)
    except Exception:
        return ([], 350.0)


# ==============================================================================
# 2. SHOPGOODWILL LIVE THRIFT & AUCTION CONNECTOR
# ==============================================================================

def _fetch_goodwill_detail(item_id: int) -> Dict[str, Any]:
    try:
        r = requests.get(
            f"https://buyerapi.shopgoodwill.com/api/ItemDetail/GetItemDetailModelByItemId/{item_id}",
            headers={
                "User-Agent": "Mozilla/5.0",
                "Origin": "https://shopgoodwill.com",
                "Referer": "https://shopgoodwill.com/",
            },
            timeout=6,
        )
        if r.status_code == 200 and r.text:
            return r.json()
    except Exception:
        pass
    return {}


def fetch_live_goodwill_listings(
    query: str,
    max_items: int = 4,
    item_category: str = "Guitars",
) -> List[LiveGuitarListing]:
    cat_cfg = CATEGORY_CATALOG.get(item_category, CATEGORY_CATALOG["Guitars"])
    min_price = int(cat_cfg["min_price_usd"])
    default_ship = float(cat_cfg["default_goodwill_ship_usd"])

    payload = {
        "isSize": False,
        "isWeddingCatagory": "false",
        "isMultipleCategoryIds": False,
        "isFromHeaderMenuTab": False,
        "layout": "",
        "searchText": query,
        "selectedGroup": "",
        "selectedCategoryIds": "",
        "selectedSellerIds": "",
        "lowPrice": str(min_price),
        "highPrice": "999999",
        "searchBuyNowOnly": "",
        "searchPickupOnly": "false",
        "searchNoPickupOnly": "false",
        "searchOneCentShippingOnly": "false",
        "searchDescriptions": "false",
        "searchClosedAuctions": "false",
        "closedAuctionEndingDate": "10/18/2026",
        "closedAuctionDaysBack": "7",
        "searchCanadaShipping": "false",
        "searchInternationalShippingOnly": "false",
        "sortColumn": "1",
        "page": "1",
        "pageSize": "25",
        "sortDescending": "false",
        "savedSearchId": 0,
        "useBuyerPrefs": "true",
        "searchUSOnlyShipping": "false",
        "categoryLevelNo": "1",
        "partNumber": "",
        "catIds": "",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://shopgoodwill.com",
        "Referer": "https://shopgoodwill.com/",
    }

    try:
        r = requests.post(
            "https://buyerapi.shopgoodwill.com/api/Search/ItemListing",
            json=payload,
            headers=headers,
            timeout=8,
        )
        if r.status_code != 200 or not r.text:
            return []

        items = r.json().get("searchResults", {}).get("items", [])
        filtered = []
        for it in items:
            title = it.get("title", "")
            if not _is_valid_item_title(title, item_category=item_category):
                continue
            filtered.append(it)

        results: List[LiveGuitarListing] = []
        for it in filtered[:max_items]:
            item_id = it.get("itemId")
            detail = _fetch_goodwill_detail(item_id) if item_id else {}

            title = it.get("title", f"Goodwill Auction {item_category}")
            ask_price = float(it.get("currentPrice", 0.0) or 0.0)
            if ask_price < min_price:
                continue

            photos: List[str] = []
            img_server = detail.get("imageServer", "https://shopgoodwillimages.azureedge.net/production/")
            img_str = detail.get("imageUrlString", "")
            if img_str:
                for part in img_str.split(";"):
                    part = part.strip().replace("\\", "/")
                    if part:
                        full_url = img_server.rstrip("/") + "/" + part.lstrip("/")
                        if full_url not in photos:
                            photos.append(full_url)

            if not photos and it.get("imageURL"):
                photos.append(it["imageURL"].replace("\\", "/"))

            seller_name = detail.get("sellerCompanyName") or "ShopGoodwill Thrift Branch"
            end_time = detail.get("endTime") or it.get("endTime", "")
            num_bids = it.get("numBids", 0)
            desc = _strip_html(detail.get("description", ""))

            scored = investigate_and_score_listing(
                listing_id=f"GW-{item_id}",
                platform="ShopGoodwill (Thrift)",
                title=title,
                condition="Thrift / Uninspected (See Photos)",
                seller_name=seller_name,
                location=f"Goodwill Auction ({num_bids} bids)",
                ask_price_usd=ask_price,
                shipping_usd=default_ship,
                listing_url=f"https://shopgoodwill.com/item/{item_id}",
                image_urls=photos,
                description=desc,
                item_category=item_category,
                extra_metadata={
                    "Current Bid / Price": f"${ask_price:,.2f}",
                    "Active Bids": num_bids,
                    "Auction Ends": end_time,
                    "Goodwill Seller": seller_name,
                },
            )
            if scored:
                results.append(scored)
        return results
    except Exception:
        return []


# ==============================================================================
# 3. CRAIGSLIST LOCAL CLASSIFIEDS CONNECTOR
# ==============================================================================

def fetch_live_craigslist_listings(
    query: str,
    max_items: int = 5,
    item_category: str = "Guitars",
) -> List[LiveGuitarListing]:
    encoded_q = urllib.parse.quote(query)
    url = f"https://sapi.craigslist.org/web/v8/postings/search/full?batch=133-0-360-0-0&query={encoded_q}&searchPath=msa&lang=en&cc=us"
    cat_cfg = CATEGORY_CATALOG.get(item_category, CATEGORY_CATALOG["Guitars"])
    min_price = float(cat_cfg["min_price_usd"])

    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=7)
        if r.status_code != 200:
            return []

        data = r.json().get("data", {})
        decode = data.get("decode", {})
        locations = decode.get("locations", [])
        items = data.get("items", [])

        q_tokens = [
            t.lower()
            for t in re.findall(r"[A-Za-z0-9]+", query)
            if len(t) >= 3 and t.lower() not in {"guitar", "guitars", "electric", "acoustic"}
        ]
        results: List[LiveGuitarListing] = []
        for raw_item in items:
            if not isinstance(raw_item, list) or len(raw_item) < 6:
                continue
            title = raw_item[-1] if isinstance(raw_item[-1], str) else ""
            if not title or not _is_valid_item_title(title, item_category=item_category):
                continue
            if q_tokens and not any(qt in title.lower() for qt in q_tokens):
                continue

            price_val = raw_item[3]
            if not isinstance(price_val, (int, float)) or price_val < min_price:
                continue

            photos: List[str] = []
            slug = "music-gear-listing"
            view_token = ""

            for elem in raw_item:
                if isinstance(elem, list) and len(elem) >= 2:
                    tag = elem[0]
                    if tag == 4:
                        for img_code in elem[1:]:
                            if isinstance(img_code, str) and ":" in img_code:
                                clean_code = img_code.split(":", 1)[1]
                                photos.append(f"https://images.craigslist.org/{clean_code}_600x450.jpg")
                    elif tag == 6 and isinstance(elem[1], str):
                        slug = elem[1]
                    elif tag == 13 and isinstance(elem[1], str):
                        view_token = elem[1]

            if not photos:
                continue

            loc_str = "Midwest / Local Pickup"
            loc_field = raw_item[4] if isinstance(raw_item[4], str) else ""
            if ":" in loc_field:
                parts = loc_field.split("~")[0].split(":")
                try:
                    loc_idx = int(parts[0])
                    if 0 < loc_idx < len(locations) and isinstance(locations[loc_idx], list):
                        loc_str = locations[loc_idx][1].title()
                except Exception:
                    pass

            post_url = (
                f"https://www.craigslist.org/view/d/{slug}/{view_token}"
                if view_token
                else f"https://cincinnati.craigslist.org/search/msa?query={encoded_q}"
            )

            scored = investigate_and_score_listing(
                listing_id=f"CL-{raw_item[0]}",
                platform="Craigslist (Local)",
                title=title,
                condition="Used (Local Owner)",
                seller_name=f"Private Seller ({loc_str})",
                location=loc_str,
                ask_price_usd=float(price_val),
                shipping_usd=0.00,
                listing_url=post_url,
                image_urls=photos,
                description=(
                    f"Live Craigslist musical instruments listing in {loc_str}. "
                    f"Local cash pickup eliminates inbound shipping costs ($0.00 shipping)."
                ),
                item_category=item_category,
                extra_metadata={
                    "Region Hub": loc_str,
                    "Pickup Shipping": "$0.00 (Local Pickup)",
                    "Photos Attached": len(photos),
                },
            )
            if scored:
                results.append(scored)
            if len(results) >= max_items + 3:
                break

        return results
    except Exception:
        return []


# ==============================================================================
# 4. CROSS-PLATFORM DEEP SEARCH LINKS (FB Marketplace, eBay, Auctions, Thrift)
# ==============================================================================

def build_external_platform_search_links(query: str) -> List[Dict[str, str]]:
    q = urllib.parse.quote(query)
    return [
        {
            "platform": "Facebook Marketplace",
            "badge": "Local Pickup",
            "url": f"https://www.facebook.com/marketplace/search/?query={q}&sortBy=price_ascend",
            "desc": "Local owner listings sorted low-to-high",
        },
        {
            "platform": "eBay (Ending Soon Auctions)",
            "badge": "Auction Snipes",
            "url": f"https://www.ebay.com/sch/i.html?_nkw={q}&_sacat=619&LH_Auction=1&_sop=1",
            "desc": "Live eBay auctions ending soonest",
        },
        {
            "platform": "eBay (Newly Listed Buy-It-Now)",
            "badge": "Fast Flips",
            "url": f"https://www.ebay.com/sch/i.html?_nkw={q}&_sacat=619&LH_BIN=1&_sop=10",
            "desc": "Newly listed underpriced Buy-It-Now posts",
        },
        {
            "platform": "ShopGoodwill Auctions",
            "badge": "Thrift Auctions",
            "url": f"https://shopgoodwill.com/categories/listing?st={q}&sg=&c=&s=&lp=25&hp=999999&sbn=&spo=false&snpo=false&socs=false&sd=false&sca=false&caed=10%2F18%2F2026&cadb=7&scs=false&sis=false&col=1&p=1&ps=40&desc=false&ss=0&UseBuyerPrefs=true&sus=false&cln=1&catIds=",
            "desc": "Nationwide Goodwill thrift store online auctions",
        },
        {
            "platform": "HiBid Estate & Liquidation Auctions",
            "badge": "Estate Auctions",
            "url": f"https://hibid.com/lots?q={q}",
            "desc": "Local & national estate sale auction lots",
        },
        {
            "platform": "Guitar Center Used Gear",
            "badge": "Used Inventory",
            "url": f"https://www.guitarcenter.com/Used/?Ntt={q}&Ns=pLH",
            "desc": "Nationwide GC used inventory sorted low-to-high",
        },
    ]


# ==============================================================================
# 5. UNIFIED PARALLEL MULTI-PLATFORM SCANNER WITH DEDUPLICATION
# ==============================================================================

def scan_all_live_platforms(
    query: str,
    include_reverb: bool = True,
    include_goodwill: bool = True,
    include_craigslist: bool = True,
    max_per_platform: int = 4,
    item_category: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_category = item_category or infer_category_from_query(query)
    raw_listings: List[LiveGuitarListing] = []
    live_median_comp = 350.0

    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_rev = (
            pool.submit(fetch_live_reverb_listings, query, max_per_platform, resolved_category)
            if include_reverb
            else None
        )
        fut_gw = (
            pool.submit(fetch_live_goodwill_listings, query, max_per_platform, resolved_category)
            if include_goodwill
            else None
        )
        fut_cl = (
            pool.submit(fetch_live_craigslist_listings, query, max_per_platform + 1, resolved_category)
            if include_craigslist
            else None
        )

        if fut_rev:
            rev_items, live_median_comp = fut_rev.result()
            raw_listings.extend(rev_items)
        if fut_gw:
            raw_listings.extend(fut_gw.result())
        if fut_cl:
            raw_listings.extend(fut_cl.result())

    clean_listings, duplicates_removed = deduplicate_listings(raw_listings)

    def _sort_key(item: LiveGuitarListing) -> Tuple[int, float]:
        is_flagged = 0 if "Clone / Unverified" in item.canonical_model or "REPLICA" in item.signal else 1
        return (is_flagged, item.net_roi_pct)

    clean_listings.sort(key=_sort_key, reverse=True)

    return {
        "query": query,
        "item_category": resolved_category,
        "live_median_comp_usd": live_median_comp,
        "total_live_listings": len(clean_listings),
        "duplicates_removed": duplicates_removed,
        "listings": clean_listings,
        "external_search_links": build_external_platform_search_links(query),
    }


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for cat, br in [("Guitars", "Gretsch"), ("Guitar Pedals & Effects", "Boss"), ("Microphones & Studio Audio", "Shure")]:
        q = build_category_brand_query(cat, br)
        res = scan_all_live_platforms(q, max_per_platform=3, item_category=cat)
        print(f"\n=== [{cat}] Query: '{q}' | Found: {res['total_live_listings']} ===")
        for l in res["listings"][:4]:
            print(
                f"  [{l.platform}] {l.title[:50]} | Ask: ${l.ask_price_usd:,.2f} | Comp: ${l.estimated_comp_usd:,.2f} | "
                f"Rec Offer: ${l.recommended_offer_usd:,.2f} (Max Bid: ${l.max_offer_usd:,.2f}) | Net: ${l.estimated_net_profit_usd:+,.2f} [{l.signal}]"
            )
