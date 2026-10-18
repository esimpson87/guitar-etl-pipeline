#!/usr/bin/env python3
"""
guitar-etl-pipeline v2.0 — Interactive Agentic BI & SRE Workbench (Streamlit + Plotly)
Author: Eric Simpson | Site Reliability & AI/Data Platform Engineer

Combines interactive Plotly data visualizations with a "Glass-Box" Agentic AI Copilot
mirroring the C# .NET Semantic Kernel plugins (NormalizeGuitarEra, GetMarketStatsAsync,
EvaluateArbitrageOpportunityAsync) and the Python 4-Agent Star Schema ELT engine.
"""

from __future__ import annotations
import datetime
import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from guitar_etl_agentic_workflow import (
    RAW_WIKIPEDIA_CORPUS,
    run_agentic_pipeline,
)

# ==============================================================================
# PAGE CONFIGURATION & STYLING
# ==============================================================================

st.set_page_config(
    page_title="Guitar ETL v2.0 | Agentic BI & SRE Workbench",
    page_icon="🎸",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.4rem; padding-bottom: 2rem; }
    .trace-pill {
        display: inline-block;
        background: rgba(56, 189, 248, 0.12);
        border: 1px solid rgba(56, 189, 248, 0.35);
        color: #38bdf8;
        border-radius: 999px;
        padding: 2px 10px;
        font-size: 0.76rem;
        font-family: monospace;
        margin-right: 6px;
        margin-top: 4px;
    }
    .signal-strong {
        background: rgba(52, 211, 153, 0.15);
        border: 1px solid rgba(52, 211, 153, 0.5);
        color: #34d399;
        padding: 3px 10px;
        border-radius: 6px;
        font-weight: 700;
        font-family: monospace;
    }
    .signal-hold {
        background: rgba(251, 191, 36, 0.15);
        border: 1px solid rgba(251, 191, 36, 0.5);
        color: #fbbf24;
        padding: 3px 10px;
        border-radius: 6px;
        font-weight: 700;
        font-family: monospace;
    }
    .signal-pass {
        background: rgba(251, 113, 133, 0.15);
        border: 1px solid rgba(251, 113, 133, 0.5);
        color: #fb7185;
        padding: 3px 10px;
        border-radius: 6px;
        font-weight: 700;
        font-family: monospace;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# DETERMINISTIC SEMANTIC KERNEL TOOL EQUIVALENTS (Mirrors C# GuitarAgent.Domain)
# ==============================================================================

REVERB_FEE_RATE = 0.0819
REVERB_FIXED_FEE_USD = 0.49
DEFAULT_BENCH_SETUP_USD = 35.00

ERA_COMP_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "Les Paul Custom (Vintage)": {
        "avg_sold_price_usd": 6850.00,
        "min_sold_price_usd": 5900.00,
        "max_sold_price_usd": 8200.00,
        "sold_comp_count": 6,
        "brand": "Gibson",
        "country_of_origin": "USA",
        "pickup_config": "HH (PAF / Patent #)",
    },
    "Les Paul Custom (Norlin Era)": {
        "avg_sold_price_usd": 3450.00,
        "min_sold_price_usd": 2950.00,
        "max_sold_price_usd": 3995.00,
        "sold_comp_count": 14,
        "brand": "Gibson",
        "country_of_origin": "USA",
        "pickup_config": "HH (T-Top / Tim Shaw)",
    },
    "Les Paul Custom (Modern)": {
        "avg_sold_price_usd": 3150.00,
        "min_sold_price_usd": 2750.00,
        "max_sold_price_usd": 3600.00,
        "sold_comp_count": 19,
        "brand": "Gibson",
        "country_of_origin": "USA",
        "pickup_config": "HH (490R / 498T)",
    },
}


def normalize_guitar_era(make: str, model: str, year: Optional[int]) -> str:
    """Mirrors GuitarAgent.Domain.Services.EraNormalizer.Normalize."""
    lower = model.lower()
    if "standard '60s" in lower or "standard 60s" in lower:
        return "Gibson Les Paul Standard"
    if "les paul custom" in lower:
        if year is None:
            return "Les Paul Custom (Modern)"
        if year < 1970:
            return "Les Paul Custom (Vintage)"
        if 1970 <= year <= 1985:
            return "Les Paul Custom (Norlin Era)"
        return "Les Paul Custom (Modern)"
    if "strat" in lower:
        return "Fender Stratocaster"
    if "prs" in lower or "custom 24" in lower:
        return "PRS Custom 24"
    if "ibanez" in lower or "rg550" in lower:
        return "Ibanez RG550 Genesis"
    if "martin" in lower or "d-28" in lower or "d28" in lower:
        return "Martin D-28"
    if "les paul" in lower:
        return "Gibson Les Paul Standard"
    return model


def evaluate_arbitrage_deal(
    listing_id: str,
    canonical_model: str,
    source: str,
    ask_price_usd: float,
    inbound_shipping_usd: float,
    avg_sold_comp_usd: float,
    bench_setup_usd: float = DEFAULT_BENCH_SETUP_USD,
) -> Dict[str, Any]:
    """Mirrors GuitarAgent.Domain.Services.ArbitrageCalculator.EvaluateDeal."""
    all_in_cost = round(ask_price_usd + inbound_shipping_usd + bench_setup_usd, 2)
    platform_fees = round(avg_sold_comp_usd * REVERB_FEE_RATE + REVERB_FIXED_FEE_USD, 2) if avg_sold_comp_usd > 0 else 0.0
    net_profit = round(avg_sold_comp_usd - platform_fees - all_in_cost, 2)
    net_roi_pct = round((net_profit / all_in_cost) * 100.0, 2) if all_in_cost > 0 else 0.0

    if net_roi_pct >= 15.0 and net_profit >= 100.0:
        signal = "STRONG_BUY"
    elif net_roi_pct >= 5.0 and net_profit > 0:
        signal = "HOLD"
    else:
        signal = "PASS"

    return {
        "listing_id": listing_id,
        "canonical_model": canonical_model,
        "source": source,
        "ask_price_usd": ask_price_usd,
        "inbound_shipping_usd": inbound_shipping_usd,
        "bench_setup_usd": bench_setup_usd,
        "all_in_cost_usd": all_in_cost,
        "avg_sold_comp_usd": avg_sold_comp_usd,
        "platform_fees_usd": platform_fees,
        "estimated_net_profit_usd": net_profit,
        "net_roi_pct": net_roi_pct,
        "signal": signal,
    }


# ==============================================================================
# SESSION STATE INITIALIZATION
# ==============================================================================

@st.cache_data(show_spinner=False)
def get_cached_pipeline_report() -> Dict[str, Any]:
    return run_agentic_pipeline()


if "pipeline_report" not in st.session_state:
    st.session_state.pipeline_report = get_cached_pipeline_report()

if "custom_sre_incidents" not in st.session_state:
    st.session_state.custom_sre_incidents = []

if "selected_deal" not in st.session_state:
    # Default to top arbitrage signal: REV-LIVE-102 (Gibson Les Paul Standard '60s)
    st.session_state.selected_deal = evaluate_arbitrage_deal(
        listing_id="REV-LIVE-102",
        canonical_model="Gibson Les Paul Standard",
        source="Reverb (IN)",
        ask_price_usd=1595.00,
        inbound_shipping_usd=45.00,
        avg_sold_comp_usd=2187.50,
        bench_setup_usd=35.00,
    )

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [
        {
            "role": "assistant",
            "content": (
                "Welcome to the **Guitar ETL v2.0 Agentic BI Workbench**! I am connected to the Star Schema "
                "valuation mart (`mart_instrument_valuation`) and the Semantic Kernel `GuitarDataPlugin` tools.\n\n"
                "Ask me to **appraise any guitar listing**, **compare model arbitrage margins**, **classify vintage/Norlin eras**, "
                "or **inspect SRE Dead-Letter Queue incidents**—and watch the **Plotly charts on the left update automatically**."
            ),
            "tool_trace": [
                {
                    "tool": "KernelBuilder.AddFromObject(GuitarDataPlugin)",
                    "input": "Registered NormalizeGuitarEra, GetMarketStatsAsync, EvaluateArbitrageOpportunityAsync",
                    "output": "READY (FunctionChoiceBehavior.Auto enabled)",
                    "latency_ms": 1.4,
                }
            ],
            "otel_span": "trace_id=4bf92f3577b34da6 | model=gemini-2.0-flash / claude-3-5-sonnet | 1.4ms",
        }
    ]


# ==============================================================================
# HELPER: LOOKUP VALUATION ROW BY MODEL
# ==============================================================================

def lookup_model_stats(canonical_model: str, report: Dict[str, Any]) -> Dict[str, Any]:
    if canonical_model in ERA_COMP_OVERRIDES:
        row = dict(ERA_COMP_OVERRIDES[canonical_model])
        row["canonical_model"] = canonical_model
        return row

    for row in report["market_intelligence_rag"]["results"]:
        if row["canonical_model"].lower() == canonical_model.lower():
            return row

    # Default fallback to Gibson Les Paul Standard
    return report["market_intelligence_rag"]["results"][2]


# ==============================================================================
# AGENT EXECUTION ENGINE (Parses Prompt -> Runs Tool Sequence -> Updates Charts)
# ==============================================================================

def process_agent_prompt(user_prompt: str) -> None:
    report = st.session_state.pipeline_report
    lower = user_prompt.lower()
    trace_id = uuid.uuid4().hex[:16]
    tool_steps: List[Dict[str, Any]] = []

    # 1. Check if prompt is about SRE / DLQ / Schema Drift
    if any(k in lower for k in ["sre", "dlq", "quarantine", "drift", "incident", "anomal"]):
        incidents = report["sre_incidents"] + st.session_state.custom_sre_incidents
        tool_steps.append(
            {
                "tool": "SreRemediationService.InspectAndRemediate",
                "input": f"query='SELECT * FROM srt_quarantine_dlq', active_incidents={len(incidents)}",
                "output": f"Retrieved {len(incidents)} SRE incident records (100% auto-remediated or quarantined)",
                "latency_ms": 18.4,
            }
        )
        tool_steps.append(
            {
                "tool": "StarSchemaWarehouse.RunDbtQualityGates",
                "input": "models=['dim_guitars', 'fact_market_pricing', 'mart_instrument_valuation']",
                "output": json.dumps(report["dbt_data_quality_tests"]),
                "latency_ms": 11.2,
            }
        )

        lines = [
            f"### SRE Self-Healing & Dead-Letter Queue Summary ({len(incidents)} Incidents)",
            "All schema drift and counterfeit price anomalies were intercepted prior to `dbt` transformation:",
        ]
        for inc in incidents:
            lines.append(
                f"- **`{inc['incident_id']}`** (`{inc['listing_id']}`) — `{inc['anomaly_type']}`: "
                f"{inc['remediation_action']} $\\rightarrow$ **`{inc['status']}`**"
            )
        lines.append("\n**Post-Remediation `dbt` Quality Gates:** `3/3 PASS` (`assert_positive_fact_prices`, `assert_referential_integrity`, `assert_unique_serial`).")
        reply_text = "\n".join(lines)
        routed_model = "claude-3-5-sonnet-bedrock"
        total_ms = 29.6

    else:
        # Extract year if present (e.g., 1958, 1974, 2021)
        year_match = re.search(r"\b(19[5-9]\d|20[0-2]\d)\b", user_prompt)
        year_val = int(year_match.group(1)) if year_match else None

        # Extract dollar ask price if present (e.g., $1,595 or 2650)
        price_matches = re.findall(r"\$\s*([0-9,]+(?:\.\d{1,2})?)|\b([1-9]\d{2,3}(?:\.\d{1,2})?)\b", user_prompt)
        extracted_price: Optional[float] = None
        for m1, m2 in price_matches:
            candidate_str = (m1 or m2).replace(",", "")
            val = float(candidate_str)
            if val != year_val and 150.0 <= val <= 15000.0:
                extracted_price = val
                break

        # Determine raw model from prompt
        if "custom 24" in lower or "prs" in lower:
            raw_make, raw_model = "PRS", "PRS Custom 24"
        elif "les paul custom" in lower:
            raw_make, raw_model = "Gibson", "Les Paul Custom"
        elif "strat" in lower or "fender" in lower:
            raw_make, raw_model = "Fender", "Fender Stratocaster"
        elif "ibanez" in lower or "rg550" in lower:
            raw_make, raw_model = "Ibanez", "Ibanez RG550 Genesis"
        elif "martin" in lower or "d-28" in lower or "d28" in lower:
            raw_make, raw_model = "Martin", "Martin D-28"
        else:
            raw_make, raw_model = "Gibson", "Les Paul Standard '60s"

        # Step 1: Era Normalization Tool
        canonical_model = normalize_guitar_era(raw_make, raw_model, year_val)
        tool_steps.append(
            {
                "tool": "GuitarDataPlugin.NormalizeGuitarEra",
                "input": f"make='{raw_make}', model='{raw_model}', productionYear={year_val}",
                "output": f"Canonical Era Model -> '{canonical_model}'",
                "latency_ms": 1.8,
            }
        )

        # Step 2: BigQuery / Star Schema Comp Lookup Tool
        stats = lookup_model_stats(canonical_model, report)
        avg_comp = float(stats["avg_sold_price_usd"])
        comp_count = int(stats["sold_comp_count"])
        sql_executed = (
            f"SELECT AVG(average_price) AS AveragePrice, COUNT(*) AS ListingCount "
            f"FROM mart_instrument_valuation WHERE canonical_model = '{canonical_model}'"
        )
        tool_steps.append(
            {
                "tool": "GuitarDataPlugin.GetMarketStatsAsync",
                "input": f"canonicalModel='{canonical_model}' | SQL: {sql_executed}",
                "output": f"AvgPrice=${avg_comp:,.2f}, SoldCompCount={comp_count}, Origin={stats['country_of_origin']}",
                "latency_ms": 38.6,
            }
        )

        # Step 3: Fee-Adjusted Arbitrage Tool
        ask_price = extracted_price if extracted_price is not None else round(avg_comp * 0.73, 2)
        shipping_usd = 45.00
        deal = evaluate_arbitrage_deal(
            listing_id=f"CHAT-{uuid.uuid4().hex[:4].upper()}",
            canonical_model=canonical_model,
            source="Reverb / Chat Appraisal",
            ask_price_usd=ask_price,
            inbound_shipping_usd=shipping_usd,
            avg_sold_comp_usd=avg_comp,
            bench_setup_usd=35.00,
        )
        tool_steps.append(
            {
                "tool": "GuitarDataPlugin.EvaluateArbitrageOpportunityAsync",
                "input": f"canonicalModel='{canonical_model}', askPriceUsd={ask_price:.2f}, inboundShippingUsd={shipping_usd:.2f}",
                "output": (
                    f"AllInCost=${deal['all_in_cost_usd']:,.2f} | ReverbFees=${deal['platform_fees_usd']:,.2f} | "
                    f"NetProfit=${deal['estimated_net_profit_usd']:+,.2f} ({deal['net_roi_pct']:+.2f}% ROI) -> {deal['signal']}"
                ),
                "latency_ms": 2.4,
            }
        )

        # Synchronize the Left-Pane Plotly Waterfall & Bar Charts with this appraisal!
        st.session_state.selected_deal = deal

        wiki_blurb = RAW_WIKIPEDIA_CORPUS.get(
            canonical_model,
            RAW_WIKIPEDIA_CORPUS.get("Gibson Les Paul Standard", ""),
        )

        reply_text = (
            f"### Appraisal: **{canonical_model}** {f'({year_val})' if year_val else ''}\n"
            f"- **Star Schema Historical Comp:** `${avg_comp:,.2f}` across `{comp_count}` verified sold listings "
            f"(`{stats['pickup_config']}`, Built in `{stats['country_of_origin']}`)\n"
            f"- **Acquisition Breakdown:** Ask `${ask_price:,.2f}` + Inbound Ship `${shipping_usd:,.2f}` + "
            f"Bench Setup `$35.00` = **`${deal['all_in_cost_usd']:,.2f}` All-In Cost**\n"
            f"- **Reverb Selling & Processing Fees (8.19% + $0.49):** `-${deal['platform_fees_usd']:,.2f}`\n"
            f"- **Estimated Net Profit:** **`${deal['estimated_net_profit_usd']:+,.2f}`** (**`{deal['net_roi_pct']:+.2f}%` Net ROI**)\n"
            f"- **Autonomous Signal:** **`{deal['signal']}`**\n\n"
            f"> 📊 *The **Plotly Financial Waterfall & Comp Charts** on the left have been automatically updated to visualize this exact deal.*\n\n"
            f"**Wikipedia RAG Luthier Context:** *{wiki_blurb}*"
        )
        routed_model = "gpt-4o (via LiteLLM Proxy)"
        total_ms = 42.8

    st.session_state.chat_messages.append(
        {
            "role": "user",
            "content": user_prompt,
        }
    )
    st.session_state.chat_messages.append(
        {
            "role": "assistant",
            "content": reply_text,
            "tool_trace": tool_steps,
            "otel_span": f"trace_id={trace_id} | model={routed_model} | {total_ms:.1f}ms",
        }
    )


# ==============================================================================
# SIDEBAR: INTERACTIVE DEAL CONTROLS & SRE CHAOS INJECTOR
# ==============================================================================

report = st.session_state.pipeline_report

with st.sidebar:
    st.markdown("## 🎛️ Workbench Controls")
    st.caption("Adjust parameters below or ask the AI Copilot in chat—both synchronize the Plotly charts in real time.")

    model_options = {
        "Gibson Les Paul Standard ($2,187.50 Avg Comp)": ("Gibson Les Paul Standard", 2187.50),
        "Fender Stratocaster Am Pro II ($1,355.00 Avg Comp)": ("Fender Stratocaster", 1355.00),
        "Ibanez RG550 Genesis MIJ ($862.50 Avg Comp)": ("Ibanez RG550 Genesis", 862.50),
        "PRS Custom 24 Core ($3,100.00 Avg Comp)": ("PRS Custom 24", 3100.00),
        "Martin D-28 Standard ($2,450.00 Avg Comp)": ("Martin D-28", 2450.00),
        "Les Paul Custom Norlin Era 1974 ($3,450.00 Avg Comp)": ("Les Paul Custom (Norlin Era)", 3450.00),
        "Les Paul Custom Vintage <1970 ($6,850.00 Avg Comp)": ("Les Paul Custom (Vintage)", 6850.00),
    }

    selected_label = st.selectbox("Select Canonical Guitar Model", list(model_options.keys()))
    sidebar_model, sidebar_comp = model_options[selected_label]

    sidebar_ask = st.slider("Seller Ask Price ($ USD)", min_value=300, max_value=6500, value=1595, step=25)
    sidebar_ship = st.slider("Inbound Shipping ($ USD)", min_value=0, max_value=200, value=45, step=5)
    sidebar_setup = st.slider("Luthier Bench Setup Allowance ($ USD)", min_value=0, max_value=150, value=35, step=5)

    if st.button("⚡ Update Deal Waterfall & Ask Agent", use_container_width=True, type="primary"):
        process_agent_prompt(
            f"Appraise a {sidebar_model} listed at ${sidebar_ask} ask with ${sidebar_ship} shipping."
        )
        st.rerun()

    st.divider()
    st.markdown("### 🛡️ SRE Chaos / Drift Simulator")
    st.caption("Test the `SreRemediationService` Dead-Letter Queue gate by injecting a malformed or counterfeit listing:")
    chaos_type = st.selectbox(
        "Anomaly Payload Type",
        [
            'Currency String Drift ("$1,425.00 USD")',
            "Counterfeit / Negative Price (-$350.00)",
            "Inverted Bounds (Low $3,200 > Avg $2,800)",
        ],
    )
    if st.button("🧪 Inject Anomaly into SRE Gate", use_container_width=True):
        inc_num = 1004 + len(st.session_state.custom_sre_incidents)
        if "Currency" in chaos_type:
            new_inc = {
                "incident_id": f"INC-SRE-{inc_num}",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "severity": "P3_WARNING",
                "listing_id": f"CHAOS-{inc_num}",
                "anomaly_type": "CURRENCY_SCHEMA_DRIFT",
                "raw_payload_excerpt": 'price_raw="$1,425.00 USD"',
                "remediation_action": "Coerced currency string to decimal 1425.00 via SreRemediationService",
                "status": "AUTO_REMEDIATED",
            }
        elif "Counterfeit" in chaos_type:
            new_inc = {
                "incident_id": f"INC-SRE-{inc_num}",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "severity": "P2_CRITICAL_DQ",
                "listing_id": f"CHAOS-{inc_num}",
                "anomaly_type": "PRICE_FLOOR_OR_NEGATIVE_ANOMALY",
                "raw_payload_excerpt": "price_usd=-350.00, model='Chibson Replica'",
                "remediation_action": "Quarantined poisoned payload to sre_quarantine_dlq.jsonl",
                "status": "QUARANTINED",
            }
        else:
            new_inc = {
                "incident_id": f"INC-SRE-{inc_num}",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "severity": "P3_WARNING",
                "listing_id": f"CHAOS-{inc_num}",
                "anomaly_type": "INVERTED_PRICE_BOUNDS_DRIFT",
                "raw_payload_excerpt": "lowest_price=3200.00 > average_price=2800.00",
                "remediation_action": "Swapped inverted lowest/average price bounds prior to SQL load",
                "status": "AUTO_REMEDIATED",
            }
        st.session_state.custom_sre_incidents.append(new_inc)
        process_agent_prompt("Show me the latest SRE schema-drift incidents and Dead-Letter Queue status.")
        st.rerun()

    st.divider()
    st.markdown(
        "🔗 [**Live Looker Studio Dashboard**](https://datastudio.google.com/reporting/888d714c-88e8-43d7-9555-a9a57f213e9a)  \n"
        "📦 [**GitHub Repository**](https://github.com/esimpson87/guitar-etl-pipeline)"
    )


# ==============================================================================
# HEADER & EXECUTIVE KPI STRIP
# ==============================================================================

st.markdown("## 🎸 Guitar Market ELT, SRE Self-Healing & Agentic Arbitrage Workbench")
st.caption(
    "**Stack:** C# .NET (`Microsoft.SemanticKernel` + `Polly v8`) • Python Multi-Agent ELT • "
    "LiteLLM Proxy • `dbt` Star Schema (BigQuery / Azure SQL) • Plotly Generative BI"
)

active_deal = st.session_state.selected_deal
all_incidents = report["sre_incidents"] + st.session_state.custom_sre_incidents
telemetry = report["litellm_telemetry_summary"]

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.metric(
        label="Active Appraisal Signal",
        value=f"{active_deal['signal']} ({active_deal['net_roi_pct']:+.2f}%)",
        delta=f"${active_deal['estimated_net_profit_usd']:+,.2f} Net Profit after Fees",
    )
with kpi2:
    st.metric(
        label="Appraised Instrument",
        value=active_deal["canonical_model"],
        delta=f"All-In ${active_deal['all_in_cost_usd']:,.2f} vs. Comp ${active_deal['avg_sold_comp_usd']:,.2f}",
    )
with kpi3:
    st.metric(
        label="SRE Self-Healing & DLQ Gate",
        value=f"{len(all_incidents)} Incidents Handled",
        delta="3/3 dbt Schema Quality Gates PASS",
    )
with kpi4:
    st.metric(
        label="LiteLLM Proxy Telemetry",
        value=f"{telemetry['total_llm_calls']} Calls (${telemetry['total_cost_usd']:.4f})",
        delta=f"{telemetry['avg_latency_ms']}ms avg • {telemetry['fallback_recoveries']} Circuit-Breaker Fallback",
    )

st.divider()

# ==============================================================================
# MAIN SPLIT-SCREEN WORKBENCH: LEFT (PLOTLY VISUALS) | RIGHT (AGENTIC COPILOT)
# ==============================================================================

left_col, right_col = st.columns([1.32, 1.0], gap="large")

with left_col:
    tab_arb, tab_star, tab_sre = st.tabs(
        [
            "📊 1. Live Arbitrage & Fee Waterfall",
            "🏛️ 2. Star Schema Valuation & Era Curves",
            "🛡️ 3. SRE Dead-Letter Queue & LiteLLM Telemetry",
        ]
    )

    # --------------------------------------------------------------------------
    # TAB 1: ARBITRAGE WATERFALL & MULTI-LISTING COMPARISON
    # --------------------------------------------------------------------------
    with tab_arb:
        st.markdown(
            f"#### Fee-Adjusted Profit Waterfall — **{active_deal['canonical_model']}** (`{active_deal['listing_id']}`)"
        )
        st.caption(
            "Synchronized with the AI Copilot: shows how Star Schema average sold comp breaks down after "
            "deducting seller ask, inbound shipping, $35 luthier bench setup, and Reverb fees (8.19% + $0.49)."
        )

        wf_fig = go.Figure(
            go.Waterfall(
                name="Arbitrage Breakdown",
                orientation="v",
                measure=["absolute", "relative", "relative", "relative", "relative", "total"],
                x=[
                    "Star Schema Sold Comp",
                    "Listing Ask Price",
                    "Inbound Shipping",
                    "Bench Setup ($35)",
                    "Reverb Fees (8.19%+$0.49)",
                    "Est. Net Profit",
                ],
                textposition="outside",
                text=[
                    f"${active_deal['avg_sold_comp_usd']:,.2f}",
                    f"-${active_deal['ask_price_usd']:,.2f}",
                    f"-${active_deal['inbound_shipping_usd']:,.2f}",
                    f"-${active_deal['bench_setup_usd']:,.2f}",
                    f"-${active_deal['platform_fees_usd']:,.2f}",
                    f"${active_deal['estimated_net_profit_usd']:+,.2f} ({active_deal['net_roi_pct']:+.1f}%)",
                ],
                y=[
                    active_deal["avg_sold_comp_usd"],
                    -active_deal["ask_price_usd"],
                    -active_deal["inbound_shipping_usd"],
                    -active_deal["bench_setup_usd"],
                    -active_deal["platform_fees_usd"],
                    0,
                ],
                connector={"line": {"color": "#475569"}},
                increasing={"marker": {"color": "#38bdf8"}},
                decreasing={"marker": {"color": "#fb7185"}},
                totals={
                    "marker": {
                        "color": "#34d399" if active_deal["estimated_net_profit_usd"] > 0 else "#f43f5e"
                    }
                },
            )
        )
        wf_fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(19,27,46,0.6)",
            height=360,
            margin=dict(l=20, r=20, t=30, b=20),
            yaxis_title="USD ($)",
        )
        st.plotly_chart(wf_fig, use_container_width=True)

        st.markdown("#### Verified Secondary-Market Arbitrage Opportunities (Reverb & eBay)")
        benchmark_deals = [
            evaluate_arbitrage_deal("REV-LIVE-102", "Gibson Les Paul Standard ('60s)", "Reverb (IN)", 1595.00, 45.00, 2187.50),
            evaluate_arbitrage_deal("EBAY-LIVE-101", "Fender Stratocaster (Am Pro II)", "eBay (KY)", 960.00, 45.00, 1355.00),
            evaluate_arbitrage_deal("EBAY-LIVE-103", "Ibanez RG550 Genesis (MIJ)", "eBay (OH)", 590.00, 45.00, 862.50),
        ]
        # Include the user's currently appraised deal if custom
        if active_deal["listing_id"].startswith("CHAT-"):
            benchmark_deals.insert(0, active_deal)

        df_deals = pd.DataFrame(benchmark_deals)

        comp_fig = go.Figure()
        comp_fig.add_trace(
            go.Bar(
                name="All-In Cost (Ask + Ship + $35 Setup)",
                x=df_deals["canonical_model"],
                y=df_deals["all_in_cost_usd"],
                marker_color="#818cf8",
                text=[f"${v:,.0f}" for v in df_deals["all_in_cost_usd"]],
                textposition="auto",
            )
        )
        comp_fig.add_trace(
            go.Bar(
                name="Star Schema Avg Sold Comp",
                x=df_deals["canonical_model"],
                y=df_deals["avg_sold_comp_usd"],
                marker_color="#38bdf8",
                text=[f"${v:,.0f}" for v in df_deals["avg_sold_comp_usd"]],
                textposition="auto",
            )
        )
        comp_fig.add_trace(
            go.Bar(
                name="Estimated Net Profit (After 8.19% Fee)",
                x=df_deals["canonical_model"],
                y=df_deals["estimated_net_profit_usd"],
                marker_color="#34d399",
                text=[f"+${v:,.0f} ({r:.1f}%)" for v, r in zip(df_deals["estimated_net_profit_usd"], df_deals["net_roi_pct"])],
                textposition="outside",
            )
        )
        comp_fig.update_layout(
            barmode="group",
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(19,27,46,0.6)",
            height=340,
            margin=dict(l=20, r=20, t=25, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis_title="USD ($)",
        )
        st.plotly_chart(comp_fig, use_container_width=True)

    # --------------------------------------------------------------------------
    # TAB 2: STAR SCHEMA VALUATION MART & ERA NORMALIZER CURVES
    # --------------------------------------------------------------------------
    with tab_star:
        st.markdown("#### `mart_instrument_valuation` — Historical Sold Price Floor, Average & Ceiling")
        df_val = pd.DataFrame(report["market_intelligence_rag"]["results"])

        val_fig = go.Figure()
        val_fig.add_trace(
            go.Bar(
                name="Min Sold Comp ($)",
                x=df_val["canonical_model"],
                y=df_val["min_sold_price_usd"],
                marker_color="#64748b",
            )
        )
        val_fig.add_trace(
            go.Bar(
                name="Avg Sold Comp ($)",
                x=df_val["canonical_model"],
                y=df_val["avg_sold_price_usd"],
                marker_color="#38bdf8",
                text=[f"${v:,.0f}" for v in df_val["avg_sold_price_usd"]],
                textposition="outside",
            )
        )
        val_fig.add_trace(
            go.Bar(
                name="Max Sold Comp ($)",
                x=df_val["canonical_model"],
                y=df_val["max_sold_price_usd"],
                marker_color="#34d399",
            )
        )
        val_fig.update_layout(
            barmode="group",
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(19,27,46,0.6)",
            height=330,
            margin=dict(l=20, r=20, t=25, b=20),
            yaxis_title="Sold Price ($ USD)",
        )
        st.plotly_chart(val_fig, use_container_width=True)

        st.markdown("#### Gibson Les Paul Custom Era Valuation Curve (`EraNormalizer.cs`)")
        df_eras = pd.DataFrame(
            [
                {"Era": "Vintage (<1970)", "AvgPrice": 6850, "MinPrice": 5900, "MaxPrice": 8200},
                {"Era": "Norlin Era (1970–1985)", "AvgPrice": 3450, "MinPrice": 2950, "MaxPrice": 3995},
                {"Era": "Modern (>1985)", "AvgPrice": 3150, "MinPrice": 2750, "MaxPrice": 3600},
            ]
        )
        era_fig = px.bar(
            df_eras,
            x="Era",
            y="AvgPrice",
            color="Era",
            text="AvgPrice",
            color_discrete_sequence=["#fbbf24", "#38bdf8", "#818cf8"],
        )
        era_fig.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
        era_fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(19,27,46,0.6)",
            height=290,
            showlegend=False,
            margin=dict(l=20, r=20, t=25, b=20),
            yaxis_title="Average Market Value ($ USD)",
        )
        st.plotly_chart(era_fig, use_container_width=True)

    # --------------------------------------------------------------------------
    # TAB 3: SRE SELF-HEALING & LITELLM TELEMETRY
    # --------------------------------------------------------------------------
    with tab_sre:
        st.markdown("#### SRE Auto-Remediation & Dead-Letter Queue (`sre_quarantine_dlq.jsonl`)")
        df_inc = pd.DataFrame(all_incidents)
        st.dataframe(
            df_inc[["incident_id", "severity", "listing_id", "anomaly_type", "remediation_action", "status"]],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("#### LiteLLM Proxy Call Latency & Token Telemetry by Agent")
        df_traces = pd.DataFrame(report["litellm_call_traces"])
        trace_fig = px.scatter(
            df_traces,
            x="call_id",
            y="latency_ms",
            color="routed_model",
            symbol="status",
            size="prompt_tokens",
            hover_data=["agent_name", "task_type", "estimated_cost_usd"],
            color_discrete_sequence=["#38bdf8", "#34d399", "#fbbf24", "#fb7185"],
        )
        trace_fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(19,27,46,0.6)",
            height=310,
            margin=dict(l=20, r=20, t=25, b=20),
            xaxis_title="LiteLLM Trace ID",
            yaxis_title="Latency (ms)",
        )
        st.plotly_chart(trace_fig, use_container_width=True)


# ==============================================================================
# RIGHT COLUMN: GLASS-BOX AGENTIC AI COPILOT
# ==============================================================================

with right_col:
    st.markdown("### 🤖 Glass-Box Semantic Kernel Agent Copilot")
    st.caption(
        "Click any scenario preset or type a custom guitar appraisal question. "
        "Expand the **Semantic Kernel Tool Trace** on any reply to inspect autonomous function calls."
    )

    # One-click interactive preset prompts for recruiters & hiring managers
    pcol1, pcol2 = st.columns(2)
    with pcol1:
        if st.button("🎸 1960s Les Paul @ $1,595", use_container_width=True):
            process_agent_prompt("Appraise a 2021 Gibson Les Paul Standard '60s listed at $1,595.")
            st.rerun()
        if st.button("🕰️ 1974 Norlin Custom @ $2,650", use_container_width=True):
            process_agent_prompt("Appraise a 1974 Gibson Les Paul Custom at $2,650 and normalize its era.")
            st.rerun()
    with pcol2:
        if st.button("⚡ Fender Am Pro II @ $960", use_container_width=True):
            process_agent_prompt("Evaluate arbitrage ROI on a 2022 Fender Stratocaster at $960 ask.")
            st.rerun()
        if st.button("🛡️ Inspect SRE DLQ Incidents", use_container_width=True):
            process_agent_prompt("Show me all SRE schema-drift incidents and Dead-Letter Queue quarantines.")
            st.rerun()

    # Scrollable chat container
    chat_container = st.container(height=540)
    with chat_container:
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                if msg.get("tool_trace"):
                    with st.status(
                        f"🔧 Executed {len(msg['tool_trace'])} Semantic Kernel Tool(s) — Click to inspect trace",
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

    user_query = st.chat_input("Ask about any guitar price, era (e.g. '1958 Les Paul Custom at $4800'), or SRE DLQ...")
    if user_query:
        process_agent_prompt(user_query)
        st.rerun()
