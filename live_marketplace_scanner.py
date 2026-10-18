#!/usr/bin/env python3
"""
live_marketplace_scanner.py
Real-time multi-platform guitar arbitrage scanner across:
  1. Reverb API (Live Used Listings + Multi-Photo Gallery + Live Market Comp Baseline)
  2. ShopGoodwill Online Thrift & Auction API (Live Goodwill Auctions + Multi-Photo Gallery)
  3. Craigslist Musical Instruments API (Live Local Owner Classifieds + Photo Gallery)
  4. Direct Cross-Platform Deep Search Generators (Facebook Marketplace, eBay, Guitar Center Used, HiBid Estate Auctions)
"""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import html
import re
import statistics
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import requests

REVERB_FEE_RATE = 0.0819
REVERB_FIXED_FEE_USD = 0.49
DEFAULT_BENCH_SETUP_USD = 35.00

EXCLUDE_KEYWORDS = (
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
    "wall hanger",
    "stand only",
    "strap only",
    "case only",
    "hard case",
    "hardshell case",
    "molded case",
    "gig bag only",
    "amp cover",
    "pedal",
    "pickup set",
    "pickups only",
)


@dataclass
class LiveGuitarListing:
    listing_id: str
    platform: str  # "Reverb", "ShopGoodwill (Thrift Auction)", "Craigslist (Local Owner)"
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
    image_urls: List[str] = field(default_factory=list)
    description: str = ""
    extra_metadata: Dict[str, Any] = field(default_factory=dict)


def _is_valid_guitar_title(title: str) -> bool:
    lower = title.lower()
    return not any(bad in lower for bad in EXCLUDE_KEYWORDS)


def _strip_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    cleaned = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    lines = [" ".join(line.split()) for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line)


def estimate_market_comp_usd(title: str, fallback_comp: float = 675.0) -> Tuple[str, float]:
    """
    Infers the specific guitar tier/sub-model from a listing title so that
    entry-level (Squier, Epiphone, Starcaster, GIO), mid-tier (MIM Player, PRS SE),
    and pro/USA tiers (Fender American Pro, Gibson Standard/Custom, PRS Core, MIJ Ibanez)
    receive accurate secondary-market resale comp baselines.
    """
    lower = title.lower()

    if "starcaster" in lower and ("fender" in lower or "strat" in lower):
        return ("Starcaster by Fender Electric", 155.00)

    if "squier" in lower or "squire" in lower:
        if "classic vibe" in lower or "40th" in lower:
            return ("Squier Classic Vibe Series", 365.00)
        if "paranormal" in lower or "contemporary" in lower:
            return ("Squier Paranormal / Contemporary", 320.00)
        if "affinity" in lower:
            return ("Squier Affinity Series", 175.00)
        return ("Squier by Fender Electric", 165.00)

    if "epiphone" in lower:
        if "1959" in lower or "inspired by gibson" in lower or "custom" in lower or "prophecy" in lower:
            return ("Epiphone Inspired by Gibson / Custom", 640.00)
        if "special" in lower or "les paul sl" in lower or "junior" in lower:
            return ("Epiphone Les Paul Special / Junior", 185.00)
        return ("Epiphone Standard Series", 435.00)

    if "gibson" in lower:
        if "custom shop" in lower or "vos" in lower or "historic" in lower or "r8" in lower or "r9" in lower:
            return ("Gibson Custom Shop Reissue", 4450.00)
        if "les paul custom" in lower:
            return ("Gibson Les Paul Custom (USA)", 3450.00)
        if "les paul standard" in lower or "standard '50s" in lower or "standard '60s" in lower or "standard 50s" in lower or "standard 60s" in lower:
            return ("Gibson Les Paul Standard (USA)", 2250.00)
        if "les paul classic" in lower or "traditional" in lower:
            return ("Gibson Les Paul Classic / Traditional (USA)", 1850.00)
        if "les paul studio" in lower or "tribute" in lower or "faded" in lower or "special" in lower:
            return ("Gibson Les Paul Studio / Tribute (USA)", 1095.00)
        if "sg standard" in lower:
            return ("Gibson SG Standard (USA)", 1495.00)
        if "sg special" in lower or "sg tribute" in lower:
            return ("Gibson SG Special / Tribute (USA)", 995.00)
        if "es-335" in lower or "es335" in lower:
            return ("Gibson ES-335 (USA)", 2750.00)
        return ("Gibson USA Electric", 1695.00)

    if "fender" in lower:
        if "custom shop" in lower or "masterbuilt" in lower:
            return ("Fender Custom Shop", 3450.00)
        if "american ultra" in lower or "american vintage" in lower or "american original" in lower:
            return ("Fender American Ultra / Vintage (USA)", 1750.00)
        if (
            "american professional" in lower
            or "american pro" in lower
            or "american standard" in lower
            or "american performer" in lower
            or "american special" in lower
            or "usa" in lower
            or "corona" in lower
        ):
            return ("Fender American Pro / Standard (USA)", 1355.00)
        if "made in japan" in lower or "mij" in lower or "cij" in lower or "japan" in lower or "aerodyne" in lower:
            return ("Fender MIJ / Japan Series", 1050.00)
        if "vintera" in lower or "deluxe" in lower or "road worn" in lower:
            return ("Fender Vintera / Deluxe Series", 875.00)
        return ("Fender Standard / Player Series (MIM)", 675.00)

    if "prs" in lower or "paul reed smith" in lower:
        if "se " in lower or " se" in lower or "silver sky se" in lower:
            return ("PRS SE Series", 650.00)
        if "s2" in lower or "ce 24" in lower or "ce24" in lower:
            return ("PRS S2 / CE Series (Maryland USA)", 1550.00)
        return ("PRS Core Series (Maryland USA)", 3100.00)

    if "ibanez" in lower:
        if "gio" in lower or "grg" in lower or "grx" in lower:
            return ("Ibanez GIO Series", 165.00)
        if "prestige" in lower or "j.custom" in lower or "genesis" in lower or "rg550" in lower or "japan" in lower or "mij" in lower:
            return ("Ibanez MIJ Prestige / Genesis", 925.00)
        return ("Ibanez Standard RG / S Series", 460.00)

    if "martin" in lower:
        if "d-28" in lower or "d28" in lower or "hd-28" in lower or "d-18" in lower or "000-28" in lower:
            return ("Martin Standard Series USA (D-18 / D-28)", 2450.00)
        if "x series" in lower or "dx" in lower or "road series" in lower:
            return ("Martin X / Road Series", 575.00)
        return ("Martin Acoustic Guitar", 1150.00)

    return ("Used Electric / Acoustic Guitar", fallback_comp)


def _compute_arbitrage_fields(
    listing_id: str,
    platform: str,
    title: str,
    canonical_model: str,
    condition: str,
    seller_name: str,
    location: str,
    ask_price_usd: float,
    shipping_usd: float,
    estimated_comp_usd: float,
    listing_url: str,
    image_urls: List[str],
    description: str,
    bench_setup_usd: float = DEFAULT_BENCH_SETUP_USD,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> LiveGuitarListing:
    all_in_cost = round(ask_price_usd + shipping_usd + bench_setup_usd, 2)
    platform_fees = round(estimated_comp_usd * REVERB_FEE_RATE + REVERB_FIXED_FEE_USD, 2)
    net_profit = round(estimated_comp_usd - platform_fees - all_in_cost, 2)
    net_roi_pct = round((net_profit / all_in_cost) * 100.0, 2) if all_in_cost > 0 else 0.0

    if net_roi_pct >= 15.0 and net_profit >= 50.0:
        signal = "STRONG_BUY"
    elif net_roi_pct >= 5.0 and net_profit > 0:
        signal = "HOLD"
    else:
        signal = "PASS"

    return LiveGuitarListing(
        listing_id=listing_id,
        platform=platform,
        title=title,
        canonical_model=canonical_model,
        condition=condition,
        seller_name=seller_name,
        location=location,
        ask_price_usd=round(ask_price_usd, 2),
        shipping_usd=round(shipping_usd, 2),
        bench_setup_usd=round(bench_setup_usd, 2),
        all_in_cost_usd=all_in_cost,
        estimated_comp_usd=round(estimated_comp_usd, 2),
        platform_fees_usd=platform_fees,
        estimated_net_profit_usd=net_profit,
        net_roi_pct=net_roi_pct,
        signal=signal,
        listing_url=listing_url,
        image_urls=image_urls,
        description=description,
        extra_metadata=extra_metadata or {},
    )


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


def fetch_live_reverb_listings(query: str, max_items: int = 4) -> Tuple[List[LiveGuitarListing], float]:
    headers = {
        "Accept-Version": "3.0",
        "Accept": "application/hal+json",
        "User-Agent": "GuitarEtl-ArbitrageScanner/2.0",
    }
    encoded_q = urllib.parse.quote(query)
    url = f"https://api.reverb.com/api/listings/all?query={encoded_q}&condition=used&per_page=35"

    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return ([], 950.0)

        raw_listings = resp.json().get("listings", [])
        valid_items = []
        prices = []

        for item in raw_listings:
            title = item.get("title", "")
            if not _is_valid_guitar_title(title):
                continue
            price_str = item.get("price", {}).get("amount")
            if not price_str:
                continue
            try:
                price_val = float(price_str)
            except ValueError:
                continue
            if price_val < 140.0:
                continue
            prices.append(price_val)
            valid_items.append((price_val, item))

        if not valid_items:
            return ([], 950.0)

        live_median_comp = round(statistics.median(prices), 2) if prices else 950.0
        valid_items.sort(key=lambda x: x[0])
        candidates = [it for _, it in valid_items[:max_items]]

        results: List[LiveGuitarListing] = []
        for item in candidates:
            lid = str(item.get("id", ""))
            detail = _fetch_reverb_detail(lid, headers) if lid else {}
            source_obj = detail if detail else item

            title = source_obj.get("title", item.get("title", "Used Guitar"))
            ask_price = float(item.get("price", {}).get("amount", 0.0))

            ship_usd = 45.0
            rates = source_obj.get("shipping", {}).get("rates", [])
            if rates and isinstance(rates, list):
                rate_amt = rates[0].get("rate", {}).get("amount")
                if rate_amt is not None:
                    try:
                        ship_usd = float(rate_amt)
                    except ValueError:
                        ship_usd = 45.0

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

            canonical_tier, tier_comp = estimate_market_comp_usd(title, live_median_comp)

            results.append(
                _compute_arbitrage_fields(
                    listing_id=f"REV-{lid}",
                    platform="Reverb",
                    title=title,
                    canonical_model=canonical_tier,
                    condition=cond,
                    seller_name=shop_name,
                    location=loc_str,
                    ask_price_usd=ask_price,
                    shipping_usd=ship_usd,
                    estimated_comp_usd=tier_comp,
                    listing_url=web_url,
                    image_urls=photos,
                    description=desc,
                    extra_metadata={
                        "Make": source_obj.get("make", ""),
                        "Model": source_obj.get("model", ""),
                        "Year": source_obj.get("year", "Unknown"),
                        "Finish": source_obj.get("finish", ""),
                        "Reverb Sample Median": f"${live_median_comp:,.2f}",
                    },
                )
            )

        return (results, live_median_comp)
    except Exception:
        return ([], 950.0)


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


def fetch_live_goodwill_listings(query: str, fallback_comp: float = 450.0, max_items: int = 4) -> List[LiveGuitarListing]:
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
        "lowPrice": "40",
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
            if not _is_valid_guitar_title(title):
                continue
            if "guitar" not in title.lower() and not any(
                b in title.lower()
                for b in ("fender", "gibson", "squier", "epiphone", "ibanez", "prs", "martin", "taylor", "yamaha", "jackson", "gretsch")
            ):
                continue
            filtered.append(it)

        results: List[LiveGuitarListing] = []
        for it in filtered[:max_items]:
            item_id = it.get("itemId")
            detail = _fetch_goodwill_detail(item_id) if item_id else {}

            title = it.get("title", "Goodwill Auction Guitar")
            ask_price = float(it.get("currentPrice", 0.0) or 0.0)
            shipping_usd = 28.00

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

            canonical_tier, tier_comp = estimate_market_comp_usd(title, fallback_comp)

            results.append(
                _compute_arbitrage_fields(
                    listing_id=f"GW-{item_id}",
                    platform="ShopGoodwill (Thrift)",
                    title=title,
                    canonical_model=canonical_tier,
                    condition="Thrift / Uninspected (See Photos)",
                    seller_name=seller_name,
                    location=f"Goodwill Auction ({num_bids} bids)",
                    ask_price_usd=ask_price,
                    shipping_usd=shipping_usd,
                    estimated_comp_usd=tier_comp,
                    listing_url=f"https://shopgoodwill.com/item/{item_id}",
                    image_urls=photos,
                    description=desc,
                    extra_metadata={
                        "Current Bid / Price": f"${ask_price:,.2f}",
                        "Active Bids": num_bids,
                        "Auction Ends": end_time,
                        "Goodwill Seller": seller_name,
                    },
                )
            )
        return results
    except Exception:
        return []


# ==============================================================================
# 3. CRAIGSLIST LOCAL CLASSIFIEDS CONNECTOR
# ==============================================================================

def fetch_live_craigslist_listings(query: str, fallback_comp: float = 675.0, max_items: int = 4) -> List[LiveGuitarListing]:
    encoded_q = urllib.parse.quote(query)
    url = f"https://sapi.craigslist.org/web/v8/postings/search/full?batch=133-0-360-0-0&query={encoded_q}&searchPath=msa&lang=en&cc=us"

    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=7)
        if r.status_code != 200:
            return []

        data = r.json().get("data", {})
        decode = data.get("decode", {})
        locations = decode.get("locations", [])
        items = data.get("items", [])

        results: List[LiveGuitarListing] = []
        for raw_item in items:
            if not isinstance(raw_item, list) or len(raw_item) < 6:
                continue
            title = raw_item[-1] if isinstance(raw_item[-1], str) else ""
            if not title or not _is_valid_guitar_title(title):
                continue

            price_val = raw_item[3]
            if not isinstance(price_val, (int, float)) or price_val < 75:
                continue

            photos: List[str] = []
            slug = "guitar-listing"
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

            canonical_tier, tier_comp = estimate_market_comp_usd(title, fallback_comp)

            results.append(
                _compute_arbitrage_fields(
                    listing_id=f"CL-{raw_item[0]}",
                    platform="Craigslist (Local)",
                    title=title,
                    canonical_model=canonical_tier,
                    condition="Used (Local Owner)",
                    seller_name=f"Private Seller ({loc_str})",
                    location=loc_str,
                    ask_price_usd=float(price_val),
                    shipping_usd=0.00,
                    estimated_comp_usd=tier_comp,
                    listing_url=post_url,
                    image_urls=photos,
                    description=(
                        f"Live Craigslist musical instruments listing in {loc_str}. "
                        f"Local cash pickup eliminates inbound shipping costs ($0.00 shipping). "
                        f"Click 'Open Original Listing' to view seller contact details and full post."
                    ),
                    extra_metadata={
                        "Region Hub": loc_str,
                        "Pickup Shipping": "$0.00 (Local Pickup)",
                        "Photos Attached": len(photos),
                    },
                )
            )
            if len(results) >= max_items:
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
            "url": f"https://shopgoodwill.com/categories/listing?st={q}&sg=&c=&s=&lp=40&hp=999999&sbn=&spo=false&snpo=false&socs=false&sd=false&sca=false&caed=10%2F18%2F2026&cadb=7&scs=false&sis=false&col=1&p=1&ps=40&desc=false&ss=0&UseBuyerPrefs=true&sus=false&cln=1&catIds=",
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
# 5. UNIFIED PARALLEL MULTI-PLATFORM SCANNER
# ==============================================================================

def scan_all_live_platforms(
    query: str,
    include_reverb: bool = True,
    include_goodwill: bool = True,
    include_craigslist: bool = True,
    max_per_platform: int = 4,
) -> Dict[str, Any]:
    listings: List[LiveGuitarListing] = []
    live_median_comp = 950.0

    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_rev = pool.submit(fetch_live_reverb_listings, query, max_per_platform) if include_reverb else None
        fut_gw = pool.submit(fetch_live_goodwill_listings, query, 450.0, max_per_platform) if include_goodwill else None
        fut_cl = pool.submit(fetch_live_craigslist_listings, query, 675.0, max_per_platform) if include_craigslist else None

        if fut_rev:
            rev_items, live_median_comp = fut_rev.result()
            listings.extend(rev_items)
        if fut_gw:
            listings.extend(fut_gw.result())
        if fut_cl:
            listings.extend(fut_cl.result())

    listings.sort(key=lambda x: x.net_roi_pct, reverse=True)

    return {
        "query": query,
        "live_median_comp_usd": live_median_comp,
        "total_live_listings": len(listings),
        "listings": listings,
        "external_search_links": build_external_platform_search_links(query),
    }


if __name__ == "__main__":
    res = scan_all_live_platforms("Fender Stratocaster", max_per_platform=3)
    print(f"Query: {res['query']} | Live Median Comp: ${res['live_median_comp_usd']:,.2f} | Found: {res['total_live_listings']}")
    for l in res["listings"]:
        print(
            f"  [{l.platform}] {l.listing_id} | {l.title[:50]} | Tier: {l.canonical_model} | "
            f"Ask: ${l.ask_price_usd:,.2f} | All-In: ${l.all_in_cost_usd:,.2f} | Comp: ${l.estimated_comp_usd:,.2f} | "
            f"Net: ${l.estimated_net_profit_usd:+,.2f} ({l.net_roi_pct:+.1f}%) | Photos: {len(l.image_urls)}"
        )
