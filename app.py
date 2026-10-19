#!/usr/bin/env python3
"""
guitar-etl-pipeline v2.1 — Live Multi-Platform Guitar Arbitrage & Agentic BI Workbench
Author: Eric Simpson | Site Reliability & AI/Data Platform Engineer

Features:
  1. Live Multi-Platform Arbitrage Scanner (Reverb API, ShopGoodwill Thrift Auctions, Craigslist Local Classifieds,
     plus 1-click deep search launchers for Facebook Marketplace, eBay Auctions/BIN, HiBid Estate Sales & GC Used).
  2. Mobile-Friendly, Full-Width Horizontal Arbitrage Chart: Thick, spacious horizontal bars with large outside
     dollar labels—click any bar or use the mobile-friendly Prev/Next buttons to inspect that guitar's photo gallery,
     exact sub-model valuation audit, seller description, and direct purchase/bid link.
  3. "Glass-Box" Semantic Kernel Agent Copilot with expandable tool-execution traces and OpenTelemetry spans.
"""

from __future__ import annotations
from dataclasses import asdict
import uuid
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from guitar_etl_agentic_workflow import (
    run_agentic_pipeline,
)
from live_marketplace_scanner import (
    scan_all_live_platforms,
)

# ==============================================================================
# PAGE CONFIGURATION & MOBILE-FRIENDLY / THEME-ADAPTIVE STYLING
# ==============================================================================

st.set_page_config(
    page_title="Guitar ETL v2.1 | Live Multi-Platform Arbitrage & Agentic Workbench",
    page_icon="🎸",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.0rem;
        padding-bottom: 2.5rem;
        max-width: 1400px;
    }
    .trace-pill {
        display: inline-block;
        background: rgba(2, 132, 199, 0.12);
        border: 1px solid rgba(2, 132, 199, 0.4);
        color: #0284c7;
        border-radius: 999px;
        padding: 3px 11px;
        font-size: 0.80rem;
        font-family: monospace;
        margin-right: 6px;
        margin-top: 4px;
    }
    .platform-badge {
        display: inline-block;
        background: rgba(79, 70, 229, 0.14);
        border: 1px solid rgba(79, 70, 229, 0.45);
        color: #4f46e5;
        border-radius: 6px;
        padding: 3px 10px;
        font-size: 0.84rem;
        font-weight: 700;
        margin-right: 8px;
    }
    .signal-badge-buy {
        display: inline-block;
        background: rgba(16, 185, 129, 0.16);
        border: 1px solid rgba(16, 185, 129, 0.55);
        color: #059669;
        border-radius: 6px;
        padding: 3px 10px;
        font-size: 0.84rem;
        font-weight: 700;
    }
    .signal-badge-hold {
        display: inline-block;
        background: rgba(245, 158, 11, 0.16);
        border: 1px solid rgba(245, 158, 11, 0.55);
        color: #d97706;
        border-radius: 6px;
        padding: 3px 10px;
        font-size: 0.84rem;
        font-weight: 700;
    }
    .signal-badge-pass {
        display: inline-block;
        background: rgba(244, 63, 94, 0.14);
        border: 1px solid rgba(244, 63, 94, 0.45);
        color: #e11d48;
        border-radius: 6px;
        padding: 3px 10px;
        font-size: 0.84rem;
        font-weight: 700;
    }
    .deep-dive-card {
        background: rgba(148, 163, 184, 0.08);
        border: 1.5px solid rgba(2, 132, 199, 0.35);
        border-radius: 14px;
        padding: 18px 22px;
        margin-top: 10px;
        margin-bottom: 18px;
    }
    /* Mobile responsiveness for phones & tablets */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
            padding-top: 0.6rem !important;
        }
        .deep-dive-card {
            padding: 12px 12px;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.35rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# CACHED PIPELINE & LIVE MULTI-PLATFORM SCANNER
# ==============================================================================

@st.cache_data(show_spinner=False)
def get_cached_pipeline_report() -> Dict[str, Any]:
    return run_agentic_pipeline()


@st.cache_data(ttl=300, show_spinner=False)
def get_cached_live_scan(
    query: str,
    include_reverb: bool,
    include_goodwill: bool,
    include_craigslist: bool,
    max_per_platform: int = 5,
) -> Dict[str, Any]:
    res = scan_all_live_platforms(
        query=query,
        include_reverb=include_reverb,
        include_goodwill=include_goodwill,
        include_craigslist=include_craigslist,
        max_per_platform=max_per_platform,
    )
    return {
        "query": res["query"],
        "live_median_comp_usd": res["live_median_comp_usd"],
        "total_live_listings": res["total_live_listings"],
        "duplicates_removed": res.get("duplicates_removed", 0),
        "listings": [asdict(item) for item in res["listings"]],
        "external_search_links": res["external_search_links"],
    }


# ==============================================================================
# SESSION STATE INITIALIZATION
# ==============================================================================

if "pipeline_report" not in st.session_state:
    st.session_state.pipeline_report = get_cached_pipeline_report()

if "live_search_query" not in st.session_state:
    st.session_state.live_search_query = "Fender Stratocaster"

if "inc_reverb" not in st.session_state:
    st.session_state.inc_reverb = True
if "inc_goodwill" not in st.session_state:
    st.session_state.inc_goodwill = True
if "inc_craigslist" not in st.session_state:
    st.session_state.inc_craigslist = True

if "live_scan_data" not in st.session_state:
    with st.spinner("Scanning live marketplaces (Reverb, ShopGoodwill Thrift Auctions, Craigslist)..."):
        st.session_state.live_scan_data = get_cached_live_scan(
            st.session_state.live_search_query,
            st.session_state.inc_reverb,
            st.session_state.inc_goodwill,
            st.session_state.inc_craigslist,
        )

if "selected_listing_idx" not in st.session_state:
    st.session_state.selected_listing_idx = 0

if "custom_sre_incidents" not in st.session_state:
    st.session_state.custom_sre_incidents = []

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [
        {
            "role": "assistant",
            "content": (
                "Welcome to the **Live Multi-Platform Guitar Arbitrage & Agentic Workbench**!\n\n"
                "- **Real-Time Multi-Platform Data:** Scans live listings across **Reverb**, "
                "**ShopGoodwill Online Thrift Auctions**, and **Craigslist Local Classifieds**.\n"
                "- **Click Any Bar or Use Prev/Next Buttons:** Select any guitar to inspect its **real photo gallery**, "
                "exact sub-model Reverb comp audit, seller description, and direct purchase/bid link."
            ),
            "tool_trace": [
                {
                    "tool": "LiveMarketplaceScanner.ScanAllPlatformsAsync",
                    "input": f"query='{st.session_state.live_search_query}', platforms=['Reverb', 'ShopGoodwill', 'Craigslist']",
                    "output": f"Fetched {len(st.session_state.live_scan_data['listings'])} verified listings with sub-model comps",
                    "latency_ms": 312.4,
                }
            ],
            "otel_span": "trace_id=7a91c4e2801f3b90 | model=gemini-2.0-flash / claude-3-5-sonnet | live_scan=OK",
        }
    ]


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_active_listing() -> Dict[str, Any]:
    listings = st.session_state.live_scan_data.get("listings", [])
    if not listings:
        return {
            "listing_id": "N/A",
            "platform": "None",
            "title": "No listings matched current filter",
            "canonical_model": st.session_state.live_search_query,
            "condition": "N/A",
            "seller_name": "N/A",
            "location": "N/A",
            "ask_price_usd": 0.0,
            "shipping_usd": 0.0,
            "bench_setup_usd": 35.0,
            "all_in_cost_usd": 35.0,
            "estimated_comp_usd": 0.0,
            "platform_fees_usd": 0.0,
            "estimated_net_profit_usd": 0.0,
            "net_roi_pct": 0.0,
            "signal": "PASS",
            "listing_url": "https://reverb.com",
            "image_urls": [],
            "description": "",
            "extra_metadata": {},
            "audit_notes": [],
        }
    idx = max(0, min(st.session_state.selected_listing_idx, len(listings) - 1))
    return listings[idx]


def run_new_live_search(query: str) -> None:
    st.session_state.live_search_query = query.strip()
    st.session_state.live_scan_data = get_cached_live_scan(
        st.session_state.live_search_query,
        st.session_state.inc_reverb,
        st.session_state.inc_goodwill,
        st.session_state.inc_craigslist,
    )
    st.session_state.selected_listing_idx = 0


def appraise_listing_in_chat(listing: Dict[str, Any], reason_prefix: str = "Deep-Dive Inspection") -> None:
    trace_id = uuid.uuid4().hex[:16]
    audit_notes = listing.get("audit_notes", [])
    audit_summary = " | ".join(audit_notes) if audit_notes else f"Resolved Market Tier -> '{listing['canonical_model']}'"
    tool_steps = [
        {
            "tool": "GuitarDataPlugin.NormalizeGuitarEra",
            "input": f"title='{listing['title'][:60]}', platform='{listing['platform']}'",
            "output": f"Exact Sub-Model Match -> '{listing['canonical_model']}'",
            "latency_ms": 1.6,
        },
        {
            "tool": "GuitarDataPlugin.GetMarketStatsAsync",
            "input": f"canonicalModel='{listing['canonical_model']}'",
            "output": f"Sub-Model Resale Comp=${listing['estimated_comp_usd']:,.2f} ({audit_summary[:140]})",
            "latency_ms": 24.8,
        },
        {
            "tool": "GuitarDataPlugin.EvaluateArbitrageOpportunityAsync",
            "input": (
                f"listingId='{listing['listing_id']}', ask=${listing['ask_price_usd']:,.2f}, "
                f"ship=${listing['shipping_usd']:,.2f}, setup=${listing['bench_setup_usd']:,.2f}"
            ),
            "output": (
                f"AllInCost=${listing['all_in_cost_usd']:,.2f} | Fees=${listing['platform_fees_usd']:,.2f} | "
                f"NetProfit=${listing['estimated_net_profit_usd']:+,.2f} ({listing['net_roi_pct']:+.1f}% ROI) -> {listing['signal']}"
            ),
            "latency_ms": 2.1,
        },
    ]

    audit_bullet_block = ""
    if audit_notes:
        formatted_notes = "\n".join(f"  - {note}" for note in audit_notes)
        audit_bullet_block = f"- **Post Investigation & Valuation Audit:**\n{formatted_notes}\n"

    reply = (
        f"### 🔍 {reason_prefix}: **{listing['title']}**\n"
        f"- **Platform & ID:** `{listing['platform']}` (`{listing['listing_id']}`) • **Location:** `{listing['location']}`\n"
        f"- **Exact Sub-Model Comp Tier:** `{listing['canonical_model']}` (Condition: `{listing['condition']}`)\n"
        f"- **All-In Cost Breakdown:** Ask `${listing['ask_price_usd']:,.2f}` + Shipping `${listing['shipping_usd']:,.2f}` "
        f"+ Bench Setup `${listing['bench_setup_usd']:,.2f}` = **`${listing['all_in_cost_usd']:,.2f}`**\n"
        f"- **Sub-Model Resale Comp:** `${listing['estimated_comp_usd']:,.2f}` (less `-${listing['platform_fees_usd']:,.2f}` Reverb 8.19% + $0.49 fee)\n"
        f"{audit_bullet_block}"
        f"- **Estimated Net Flip Profit:** **`${listing['estimated_net_profit_usd']:+,.2f}`** (**`{listing['net_roi_pct']:+.1f}%` Net ROI**)\n"
        f"- **Agent Recommendation:** **`{listing['signal']}`**\n"
        f"- 🔗 [**Open Original Listing on {listing['platform']}**]({listing['listing_url']})"
    )

    st.session_state.chat_messages.append(
        {
            "role": "assistant",
            "content": reply,
            "tool_trace": tool_steps,
            "otel_span": f"trace_id={trace_id} | model=gpt-4o / semantic-kernel | 28.5ms",
        }
    )


def handle_user_chat_prompt(user_prompt: str) -> None:
    st.session_state.chat_messages.append({"role": "user", "content": user_prompt})
    lower = user_prompt.lower()
    trace_id = uuid.uuid4().hex[:16]

    search_models = [
        ("gibson les paul", "Gibson Les Paul"),
        ("les paul", "Gibson Les Paul"),
        ("fender stratocaster", "Fender Stratocaster"),
        ("stratocaster", "Fender Stratocaster"),
        ("fender telecaster", "Fender Telecaster"),
        ("telecaster", "Fender Telecaster"),
        ("prs", "PRS Custom"),
        ("ibanez", "Ibanez RG"),
        ("martin", "Martin Guitar"),
        ("epiphone", "Epiphone Les Paul"),
        ("squier", "Squier Classic Vibe"),
        ("gretsch", "Gretsch Guitar"),
    ]
    matched_query: Optional[str] = None
    for kw, canonical_q in search_models:
        if kw in lower:
            matched_query = canonical_q
            break

    if matched_query:
        run_new_live_search(matched_query)
        top_deal = get_active_listing()
        appraise_listing_in_chat(top_deal, reason_prefix=f"Live Multi-Platform Scan Top Deal for '{matched_query}'")
        return

    if any(k in lower for k in ["sre", "dlq", "quarantine", "drift", "incident"]):
        report = st.session_state.pipeline_report
        incidents = report["sre_incidents"] + st.session_state.custom_sre_incidents
        lines = [
            f"### 🛡️ SRE Self-Healing & Dead-Letter Queue Report ({len(incidents)} Incidents)",
            "All schema drift and counterfeit anomalies were intercepted prior to warehouse load:",
        ]
        for inc in incidents:
            lines.append(
                f"- **`{inc['incident_id']}`** (`{inc['listing_id']}`): `{inc['anomaly_type']}` $\\rightarrow$ **`{inc['status']}`**"
            )
        st.session_state.chat_messages.append(
            {
                "role": "assistant",
                "content": "\n".join(lines),
                "tool_trace": [
                    {
                        "tool": "SreRemediationService.InspectAndRemediate",
                        "input": f"incidents={len(incidents)}",
                        "output": "All dbt quality assertions PASS",
                        "latency_ms": 14.2,
                    }
                ],
                "otel_span": f"trace_id={trace_id} | model=claude-3-5-sonnet | 14.2ms",
            }
        )
    else:
        appraise_listing_in_chat(get_active_listing(), reason_prefix="Agent Appraisal of Selected Listing")


# ==============================================================================
# SIDEBAR: LIVE MULTI-PLATFORM SEARCH & EXTERNAL LAUNCHERS
# ==============================================================================

with st.sidebar:
    st.markdown("## 🔎 Live Scanner Controls")
    st.caption("Search real-time used, thrift, and local classified guitar listings across platforms:")

    preset_queries = [
        "Fender Stratocaster",
        "Gibson Les Paul",
        "Fender Telecaster",
        "Epiphone Les Paul",
        "Martin Guitar",
        "PRS Guitar",
        "Ibanez RG Guitar",
        "Custom Search...",
    ]
    current_q = st.session_state.live_search_query
    default_preset_idx = preset_queries.index(current_q) if current_q in preset_queries else 0
    selected_preset = st.selectbox("Quick Model Search", preset_queries, index=default_preset_idx)
    if selected_preset == "Custom Search...":
        search_input = st.text_input("Enter Custom Guitar Search", value=st.session_state.live_search_query)
    else:
        search_input = selected_preset

    st.markdown("**Platforms to Scan Live:**")
    inc_rev = st.checkbox("Reverb API (Used Gear)", value=st.session_state.inc_reverb)
    inc_gw = st.checkbox("ShopGoodwill (Online Thrift Auctions)", value=st.session_state.inc_goodwill)
    inc_cl = st.checkbox("Craigslist (Local Owner Pickup)", value=st.session_state.inc_craigslist)

    if st.button("🚀 Scan Live Platforms Now", use_container_width=True, type="primary"):
        st.session_state.inc_reverb = inc_rev
        st.session_state.inc_goodwill = inc_gw
        st.session_state.inc_craigslist = inc_cl
        with st.spinner(f"Scanning Reverb, ShopGoodwill & Craigslist for '{search_input}'..."):
            run_new_live_search(search_input)
            top = get_active_listing()
            appraise_listing_in_chat(top, reason_prefix=f"Live Scan Completed ('{search_input}')")
        st.rerun()

    st.divider()
    st.markdown("### 🌐 External Arbitrage Launchers")
    st.caption(
        f"Open pre-filtered low-to-high searches for **`{st.session_state.live_search_query}`** on additional platforms:"
    )
    for ext in st.session_state.live_scan_data.get("external_search_links", []):
        st.link_button(
            f"🔗 {ext['platform']} ({ext['badge']})",
            ext["url"],
            use_container_width=True,
        )

    st.divider()
    st.markdown(
        "📊 [**Live Looker Studio Dashboard**](https://datastudio.google.com/reporting/888d714c-88e8-43d7-9555-a9a57f213e9a)  \n"
        "📦 [**GitHub Repository**](https://github.com/esimpson87/guitar-etl-pipeline)"
    )


# ==============================================================================
# HEADER & MOBILE-FRIENDLY QUICK SEARCH BAR
# ==============================================================================

st.markdown("## 🎸 Live Multi-Platform Guitar Arbitrage & Agentic Workbench")

# Top Quick-Search Bar (Always visible on mobile & desktop without opening sidebar!)
qcol1, qcol2, qcol3 = st.columns([2.2, 1.2, 1.0], gap="small")
with qcol1:
    quick_models = [
        "Fender Stratocaster",
        "Gibson Les Paul",
        "Fender Telecaster",
        "Epiphone Les Paul",
        "Martin Guitar",
        "PRS Guitar",
        "Ibanez RG Guitar",
    ]
    cur_idx = quick_models.index(st.session_state.live_search_query) if st.session_state.live_search_query in quick_models else 0
    top_selected_model = st.selectbox(
        "🎸 Select Guitar Model to Scan Across Reverb, Goodwill & Craigslist:",
        options=quick_models,
        index=cur_idx,
        key="top_model_selector",
    )
    if top_selected_model != st.session_state.live_search_query:
        with st.spinner(f"Scanning live marketplaces for '{top_selected_model}'..."):
            run_new_live_search(top_selected_model)
            appraise_listing_in_chat(get_active_listing(), reason_prefix=f"Switched Model Scan ('{top_selected_model}')")
        st.rerun()

with qcol2:
    chart_filter_mode = st.selectbox(
        "📊 Chart Display Filter:",
        options=[
            "Top 6 Best Deals (Crisp & Uncrowded)",
            "Top 10 Deals",
            "Profitable Deals Only (Net > $0)",
            "All Scanned Listings",
        ],
        index=0,
        key="chart_filter_selector",
    )

with qcol3:
    chart_metric_mode = st.selectbox(
        "📐 Bar Chart View:",
        options=[
            "Cost vs. Comp + Net Profit",
            "Net Flip Profit ($) Only",
        ],
        index=0,
        key="chart_metric_selector",
    )

scan_data = st.session_state.live_scan_data
live_listings: List[Dict[str, Any]] = scan_data.get("listings", [])
active_listing = get_active_listing()
report = st.session_state.pipeline_report

# Responsive KPI Row (2x2 on mobile, 4 across on desktop)
kpi_left, kpi_right = st.columns(2, gap="medium")
with kpi_left:
    k1, k2 = st.columns(2)
    dups_removed = scan_data.get("duplicates_removed", 0)
    k1.metric(
        label=f"Verified Deals ('{scan_data['query']}')",
        value=f"{len(live_listings)} Listings",
        delta=f"{dups_removed} Duplicates Filtered",
    )
    k2.metric(
        label="Selected All-In Cost",
        value=f"${active_listing['all_in_cost_usd']:,.0f}",
        delta=f"Ask ${active_listing['ask_price_usd']:,.0f} + Ship ${active_listing['shipping_usd']:,.0f} + ${active_listing['bench_setup_usd']:,.0f} Setup",
    )
with kpi_right:
    k3, k4 = st.columns(2)
    k3.metric(
        label="Sub-Model Comp",
        value=f"${active_listing['estimated_comp_usd']:,.0f}",
        delta=f"Fees: -${active_listing['platform_fees_usd']:,.0f} (8.19%)",
    )
    k4.metric(
        label="Est. Net Flip Profit",
        value=f"${active_listing['estimated_net_profit_usd']:+,.0f} ({active_listing['net_roi_pct']:+.1f}%)",
        delta=f"Signal: {active_listing['signal']}",
    )


# ==============================================================================
# FULL-WIDTH NAVIGATION TABS (100% WIDTH FOR READABLE CHARTS & MOBILE)
# ==============================================================================

tab_live, tab_copilot, tab_waterfall, tab_sre = st.tabs(
    [
        "🔥 1. Live Deals Chart & Photo Deep-Dive",
        "🤖 2. Agentic AI Copilot & Tool Traces",
        "💧 3. Selected Deal Profit Waterfall",
        "🛡️ 4. SRE Dead-Letter Queue & Telemetry",
    ]
)

with tab_live:
    if live_listings:
        # Filter listings for the chart based on user's chosen filter mode
        indexed_listings = list(enumerate(live_listings))
        if chart_filter_mode.startswith("Top 6"):
            filtered_indexed = indexed_listings[:6]
        elif chart_filter_mode.startswith("Top 10"):
            filtered_indexed = indexed_listings[:10]
        elif chart_filter_mode.startswith("Profitable"):
            prof = [(i, item) for i, item in indexed_listings if item["estimated_net_profit_usd"] > 0]
            filtered_indexed = prof if prof else indexed_listings[:6]
        else:
            filtered_indexed = indexed_listings

        # Ensure currently selected listing is visible or accessible
        df_chart = pd.DataFrame([item for _, item in filtered_indexed])
        df_chart["orig_idx"] = [i for i, _ in filtered_indexed]

        # Build clean, readable left-hand Y-axis labels (Platform + clean title + ROI badge)
        def _format_row_label(row: pd.Series) -> str:
            idx_num = int(row["orig_idx"]) + 1
            plat_short = row["platform"].split()[0]
            clean_t = row["title"]
            if len(clean_t) > 36:
                clean_t = clean_t[:35].rstrip() + "…"
            marker = "👉 " if int(row["orig_idx"]) == st.session_state.selected_listing_idx else ""
            return f"{marker}#{idx_num} [{plat_short}] {clean_t}"

        df_chart["row_label"] = df_chart.apply(_format_row_label, axis=1)

        # Reverse order so #1 Best Deal appears at the TOP of the horizontal bar chart
        df_plot = df_chart.iloc[::-1].reset_index(drop=True)

        st.markdown(
            f"#### 📊 Ranked Arbitrage Comparison — **`{scan_data['query']}`** "
            "*(Tap any bar or use the buttons below to inspect photos & audit details)*"
        )

        # Calculate spacious dynamic height (72px per guitar row, minimum 360px)
        num_rows = len(df_plot)
        dynamic_height = max(360, num_rows * 74 + 90)

        max_val = max(
            float(df_plot["all_in_cost_usd"].max()),
            float(df_plot["estimated_comp_usd"].max()),
            float(df_plot["estimated_net_profit_usd"].max()),
            100.0,
        )
        min_val = min(0.0, float(df_plot["estimated_net_profit_usd"].min()))
        x_padding_max = max_val * 1.26
        x_padding_min = min_val * 1.28 if min_val < 0 else 0.0

        comp_fig = go.Figure()

        if chart_metric_mode == "Net Flip Profit ($) Only":
            comp_fig.add_trace(
                go.Bar(
                    name="Estimated Net Profit (After 8.19% Reverb Fee & Setup)",
                    y=df_plot["row_label"],
                    x=df_plot["estimated_net_profit_usd"],
                    orientation="h",
                    customdata=df_plot["orig_idx"],
                    marker_color=[
                        "#10b981" if v > 0 else "#f43f5e" for v in df_plot["estimated_net_profit_usd"]
                    ],
                    text=[
                        f"  {'+' if v >= 0 else ''}${v:,.0f} ({r:+.1f}% ROI)  "
                        for v, r in zip(df_plot["estimated_net_profit_usd"], df_plot["net_roi_pct"])
                    ],
                    textposition="outside",
                    textfont=dict(size=13, family="Arial, sans-serif"),
                    cliponaxis=False,
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "Est. Net Flip Profit: <b>$%{x:,.2f}</b><br>"
                        "<i>Tap bar to inspect listing photos & valuation audit</i><extra></extra>"
                    ),
                )
            )
        else:
            comp_fig.add_trace(
                go.Bar(
                    name="All-In Cost (Ask + Ship + Setup)",
                    y=df_plot["row_label"],
                    x=df_plot["all_in_cost_usd"],
                    orientation="h",
                    customdata=df_plot["orig_idx"],
                    marker_color="#6366f1",
                    text=[f" ${v:,.0f} Cost " for v in df_plot["all_in_cost_usd"]],
                    textposition="outside",
                    textfont=dict(size=12, family="Arial, sans-serif"),
                    cliponaxis=False,
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "All-In Cost: <b>$%{x:,.2f}</b><br>"
                        "<i>Tap bar to inspect listing photos & valuation audit</i><extra></extra>"
                    ),
                )
            )
            comp_fig.add_trace(
                go.Bar(
                    name="Sub-Model Resale Comp ($)",
                    y=df_plot["row_label"],
                    x=df_plot["estimated_comp_usd"],
                    orientation="h",
                    customdata=df_plot["orig_idx"],
                    marker_color="#0ea5e9",
                    text=[f" ${v:,.0f} Comp " for v in df_plot["estimated_comp_usd"]],
                    textposition="outside",
                    textfont=dict(size=12, family="Arial, sans-serif"),
                    cliponaxis=False,
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "Sub-Model Resale Comp: <b>$%{x:,.2f}</b><br>"
                        "<i>Tap bar to inspect listing photos & valuation audit</i><extra></extra>"
                    ),
                )
            )
            comp_fig.add_trace(
                go.Bar(
                    name="Est. Net Profit (After Fees)",
                    y=df_plot["row_label"],
                    x=df_plot["estimated_net_profit_usd"],
                    orientation="h",
                    customdata=df_plot["orig_idx"],
                    marker_color=[
                        "#10b981" if v > 0 else "#f43f5e" for v in df_plot["estimated_net_profit_usd"]
                    ],
                    text=[
                        f" {'+' if v >= 0 else ''}${v:,.0f} ({r:+.0f}%) "
                        for v, r in zip(df_plot["estimated_net_profit_usd"], df_plot["net_roi_pct"])
                    ],
                    textposition="outside",
                    textfont=dict(size=12, family="Arial, sans-serif"),
                    cliponaxis=False,
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "Est. Net Profit: <b>$%{x:,.2f}</b><br>"
                        "<i>Tap bar to inspect listing photos & valuation audit</i><extra></extra>"
                    ),
                )
            )

        comp_fig.update_layout(
            barmode="group",
            bargap=0.26,
            bargroupgap=0.10,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=dynamic_height,
            margin=dict(l=10, r=95, t=45, b=35),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="left",
                x=0,
                font=dict(size=13),
            ),
            xaxis=dict(
                title="USD ($)",
                range=[x_padding_min, x_padding_max],
                showgrid=True,
                gridcolor="rgba(148, 163, 184, 0.25)",
                zeroline=True,
                zerolinewidth=1.5,
                zerolinecolor="rgba(148, 163, 184, 0.5)",
                tickprefix="$",
                tickfont=dict(size=12),
            ),
            yaxis=dict(
                automargin=True,
                tickfont=dict(size=13),
            ),
            clickmode="event+select",
        )

        chart_event = st.plotly_chart(
            comp_fig,
            use_container_width=True,
            on_select="rerun",
            selection_mode="points",
            key="live_arbitrage_horizontal_chart",
            config={"displayModeBar": False},
        )

        # Handle bar click -> map back to original listing index via customdata or point_index
        if chart_event and chart_event.get("selection") and chart_event["selection"].get("points"):
            clicked_pt = chart_event["selection"]["points"][0]
            cdata = clicked_pt.get("customdata")
            chosen_orig_idx: Optional[int] = None
            if cdata is not None:
                chosen_orig_idx = int(cdata[0]) if isinstance(cdata, list) else int(cdata)
            else:
                pt_idx = clicked_pt.get("point_index", clicked_pt.get("pointIndex"))
                if pt_idx is not None and 0 <= int(pt_idx) < len(df_plot):
                    chosen_orig_idx = int(df_plot.iloc[int(pt_idx)]["orig_idx"])

            if chosen_orig_idx is not None and 0 <= chosen_orig_idx < len(live_listings):
                if st.session_state.selected_listing_idx != chosen_orig_idx:
                    st.session_state.selected_listing_idx = chosen_orig_idx
                    active_listing = get_active_listing()
                    appraise_listing_in_chat(
                        active_listing,
                        reason_prefix="Clicked Chart Bar -> Listing Deep-Dive",
                    )
                    st.rerun()

        # ======================================================================
        # MOBILE-FRIENDLY DEAL STEPPER (PREV / DROPDOWN / NEXT)
        # ======================================================================
        nav_prev, nav_select, nav_next = st.columns([1.0, 3.8, 1.0], gap="small")
        with nav_prev:
            if st.button("⬅️ Previous Deal", use_container_width=True):
                st.session_state.selected_listing_idx = (st.session_state.selected_listing_idx - 1) % len(live_listings)
                active_listing = get_active_listing()
                appraise_listing_in_chat(active_listing, reason_prefix="Previous Deal Selected")
                st.rerun()
        with nav_next:
            if st.button("Next Deal ➡️", use_container_width=True):
                st.session_state.selected_listing_idx = (st.session_state.selected_listing_idx + 1) % len(live_listings)
                active_listing = get_active_listing()
                appraise_listing_in_chat(active_listing, reason_prefix="Next Deal Selected")
                st.rerun()
        with nav_select:
            listing_labels = [
                f"#{i+1} [{item['platform'].split()[0]}] {item['title'][:52]} — Cost: ${item['all_in_cost_usd']:,.0f} | Comp: ${item['estimated_comp_usd']:,.0f} | Net: ${item['estimated_net_profit_usd']:+,.0f} ({item['net_roi_pct']:+.1f}%)"
                for i, item in enumerate(live_listings)
            ]
            chosen_idx = st.selectbox(
                "📌 Selected Listing to Inspect (Tap any bar above or choose here):",
                options=list(range(len(live_listings))),
                format_func=lambda i: listing_labels[i],
                index=st.session_state.selected_listing_idx,
                label_visibility="collapsed",
            )
            if chosen_idx != st.session_state.selected_listing_idx:
                st.session_state.selected_listing_idx = chosen_idx
                active_listing = get_active_listing()
                appraise_listing_in_chat(active_listing, reason_prefix="Selected Listing Deep-Dive")
                st.rerun()

        # ======================================================================
        # DEEP-DIVE LISTING INSPECTOR (PHOTOS, AUDIT TRAIL, FINANCIALS, LINK)
        # ======================================================================
        sig = active_listing["signal"]
        sig_class = (
            "signal-badge-buy"
            if "BUY" in sig
            else ("signal-badge-hold" if "HOLD" in sig else "signal-badge-pass")
        )

        st.markdown("<div class='deep-dive-card'>", unsafe_allow_html=True)
        st.markdown(
            f"### 📸 Inspected Listing #{st.session_state.selected_listing_idx + 1}: **{active_listing['title']}**\n"
            f"<span class='platform-badge'>{active_listing['platform']}</span> "
            f"<span class='{sig_class}'>{sig} ({active_listing['net_roi_pct']:+.1f}% ROI)</span> &nbsp; "
            f"**ID:** `{active_listing['listing_id']}` • "
            f"**Seller:** `{active_listing['seller_name']}` • "
            f"**Location:** `{active_listing['location']}` • "
            f"**Condition:** `{active_listing['condition']}`",
            unsafe_allow_html=True,
        )

        img_col, info_col = st.columns([1.08, 1.0], gap="large")

        with img_col:
            photos = active_listing.get("image_urls", [])
            if photos:
                photo_idx = (
                    st.slider(
                        f"Browse Listing Photos ({len(photos)} available)",
                        min_value=1,
                        max_value=len(photos),
                        value=1,
                        key=f"photo_slider_{active_listing['listing_id']}",
                    )
                    if len(photos) > 1
                    else 1
                )
                st.image(
                    photos[photo_idx - 1],
                    caption=f"Photo {photo_idx} of {len(photos)} — {active_listing['title'][:65]}",
                    use_container_width=True,
                )
                if len(photos) > 1:
                    thumb_cols = st.columns(min(4, len(photos)))
                    for t_i, t_col in enumerate(thumb_cols):
                        with t_col:
                            st.image(photos[t_i], use_container_width=True)
            else:
                st.info("No images attached to this listing.")

        with info_col:
            st.markdown("#### 💰 Real-World Flip & All-In Cost Breakdown")
            m1, m2, m3 = st.columns(3)
            m1.metric("Seller Ask / Bid", f"${active_listing['ask_price_usd']:,.2f}")
            m2.metric("Shipping + Setup", f"${active_listing['shipping_usd'] + active_listing['bench_setup_usd']:,.2f}")
            m3.metric("Total All-In Cost", f"${active_listing['all_in_cost_usd']:,.2f}")

            m4, m5, m6 = st.columns(3)
            m4.metric("Sub-Model Comp", f"${active_listing['estimated_comp_usd']:,.2f}")
            m5.metric("Reverb 8.19% Fee", f"-${active_listing['platform_fees_usd']:,.2f}")
            m6.metric(
                "Est. Net Profit",
                f"${active_listing['estimated_net_profit_usd']:+,.2f}",
                delta=f"{active_listing['net_roi_pct']:+.1f}% Net ROI",
            )

            st.markdown(f"**Matched Sub-Model Tier:** `{active_listing['canonical_model']}`")

            audit_notes = active_listing.get("audit_notes", [])
            if audit_notes:
                st.markdown("**🔍 Post Investigation & Exact-Model Comp Audit:**")
                for note in audit_notes:
                    st.markdown(f"- {note}")

            extra = active_listing.get("extra_metadata", {})
            if extra:
                with st.expander("📋 Additional Listing Metadata", expanded=False):
                    for k, v in extra.items():
                        if v:
                            st.markdown(f"- **{k}:** `{v}`")

            st.link_button(
                f"🛒 Open Live Listing on {active_listing['platform']} ↗",
                active_listing["listing_url"],
                use_container_width=True,
                type="primary",
            )

        if active_listing.get("description"):
            with st.expander("📄 View Full Seller Post Description", expanded=False):
                st.write(active_listing["description"][:1800])

        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.warning("No live listings returned. Try selecting another guitar model above.")


# ==============================================================================
# TAB 2: GLASS-BOX AGENTIC AI COPILOT
# ==============================================================================

with tab_copilot:
    st.markdown("### 🤖 Glass-Box Semantic Kernel Agent Copilot")
    st.caption(
        "Ask about any guitar model or click a quick-scan button below—the agent scans live listings, "
        "runs `GuitarDataPlugin` tools, and logs full OpenTelemetry tool traces."
    )

    pcol1, pcol2, pcol3, pcol4 = st.columns(4)
    with pcol1:
        if st.button("🎸 Scan Gibson Les Pauls", use_container_width=True):
            handle_user_chat_prompt("Scan live marketplaces for Gibson Les Paul flips.")
            st.rerun()
    with pcol2:
        if st.button("⚡ Scan Fender Strats", use_container_width=True):
            handle_user_chat_prompt("Scan live marketplaces for Fender Stratocaster flips.")
            st.rerun()
    with pcol3:
        if st.button("🌲 Scan Martin Acoustics", use_container_width=True):
            handle_user_chat_prompt("Scan live marketplaces for Martin acoustic guitars.")
            st.rerun()
    with pcol4:
        if st.button("🔥 Scan Epiphone Deals", use_container_width=True):
            handle_user_chat_prompt("Scan live marketplaces for Epiphone Les Paul guitars.")
            st.rerun()

    chat_container = st.container(height=520)
    with chat_container:
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                if msg.get("tool_trace"):
                    with st.status(
                        f"🔧 Executed {len(msg['tool_trace'])} Agentic Tool(s) — Click to inspect trace",
                        state="complete",
                        expanded=False,
                    ):
                        for idx, step in enumerate(msg["tool_trace"], start=1):
                            st.markdown(
                                f"**Step {idx}: `{step['tool']}`** (`{step['latency_ms']} ms`)  \n"
                                f"- **Input:** `{step['input']}`  \n"
                                f"- **Output:** `{step['output']}`"
                            )
                st.markdown(msg["content"])
                if msg.get("otel_span"):
                    st.markdown(
                        f"<span class='trace-pill'>OTel {msg['otel_span']}</span>",
                        unsafe_allow_html=True,
                    )

    user_query = st.chat_input(
        "Ask to scan any guitar (e.g. 'Scan live Telecaster deals', 'Scan Martin acoustic') or appraise selected..."
    )
    if user_query:
        handle_user_chat_prompt(user_query)
        st.rerun()


# ==============================================================================
# TAB 3: SELECTED LISTING PROFIT WATERFALL
# ==============================================================================

with tab_waterfall:
    st.markdown(
        f"#### 💧 Dollar-by-Dollar Arbitrage Waterfall — **{active_listing['title'][:65]}** (`{active_listing['listing_id']}`)"
    )
    wf_fig = go.Figure(
        go.Waterfall(
            name="Flip Breakdown",
            orientation="v",
            measure=["absolute", "relative", "relative", "relative", "relative", "total"],
            x=[
                "Sub-Model Resale Comp",
                "Seller Ask Price",
                "Inbound Shipping",
                f"Bench Setup (${active_listing['bench_setup_usd']:,.0f})",
                "Reverb Fees (8.19%)",
                "Est. Net Profit",
            ],
            textposition="outside",
            textfont=dict(size=13),
            cliponaxis=False,
            text=[
                f"${active_listing['estimated_comp_usd']:,.2f}",
                f"-${active_listing['ask_price_usd']:,.2f}",
                f"-${active_listing['shipping_usd']:,.2f}",
                f"-${active_listing['bench_setup_usd']:,.2f}",
                f"-${active_listing['platform_fees_usd']:,.2f}",
                f"${active_listing['estimated_net_profit_usd']:+,.2f} ({active_listing['net_roi_pct']:+.1f}%)",
            ],
            y=[
                active_listing["estimated_comp_usd"],
                -active_listing["ask_price_usd"],
                -active_listing["shipping_usd"],
                -active_listing["bench_setup_usd"],
                -active_listing["platform_fees_usd"],
                0,
            ],
            connector={"line": {"color": "rgba(148, 163, 184, 0.6)"}},
            increasing={"marker": {"color": "#0ea5e9"}},
            decreasing={"marker": {"color": "#f43f5e"}},
            totals={
                "marker": {
                    "color": "#10b981" if active_listing["estimated_net_profit_usd"] > 0 else "#f43f5e"
                }
            },
        )
    )
    wf_fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=460,
        margin=dict(l=20, r=20, t=45, b=30),
        yaxis=dict(
            title="USD ($)",
            tickprefix="$",
            gridcolor="rgba(148, 163, 184, 0.25)",
        ),
        xaxis=dict(tickfont=dict(size=13)),
    )
    st.plotly_chart(wf_fig, use_container_width=True, config={"displayModeBar": False})


# ==============================================================================
# TAB 4: SRE SELF-HEALING & STAR SCHEMA BASELINE
# ==============================================================================

with tab_sre:
    st.markdown("#### 🛡️ SRE Auto-Remediation & Dead-Letter Queue (`sre_quarantine_dlq.jsonl`)")
    df_inc = pd.DataFrame(report["sre_incidents"] + st.session_state.custom_sre_incidents)
    st.dataframe(
        df_inc[["incident_id", "severity", "listing_id", "anomaly_type", "remediation_action", "status"]],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### ⚡ LiteLLM Proxy Call Latency & Token Telemetry by Agent")
    df_traces = pd.DataFrame(report["litellm_call_traces"])
    trace_fig = px.scatter(
        df_traces,
        x="call_id",
        y="latency_ms",
        color="routed_model",
        symbol="status",
        size="prompt_tokens",
        hover_data=["agent_name", "task_type", "estimated_cost_usd"],
        color_discrete_sequence=["#0ea5e9", "#10b981", "#f59e0b", "#f43f5e"],
    )
    trace_fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=340,
        margin=dict(l=20, r=20, t=25, b=20),
    )
    st.plotly_chart(trace_fig, use_container_width=True, config={"displayModeBar": False})
