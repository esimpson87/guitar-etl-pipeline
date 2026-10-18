# guitar-etl-pipeline v2.0: Autonomous Multi-Agent ELT, SRE Self-Healing & Market Arbitrage Engine

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://guitar-etl-pipeline-8vscs23jsi8xkuwrcak2ok.streamlit.app/)
![CI Status](https://github.com/esimpson87/guitar-etl-pipeline/actions/workflows/ci.yml/badge.svg)

**Author:** Eric Simpson | Site Reliability & AI/Data Platform Engineer  
**Live Application:** [guitar-etl-pipeline-8vscs23jsi8xkuwrcak2ok.streamlit.app](https://guitar-etl-pipeline-8vscs23jsi8xkuwrcak2ok.streamlit.app/)  
**Stack:** C# (.NET 8 / .NET 10) • Microsoft Semantic Kernel • Polly v8 Resilience • LiteLLM Proxy (Model Routing & Fallbacks) • dbt Core • Google BigQuery & Cloud Storage • Azure SQL Database • Streamlit & Plotly • xUnit

---

## 1. Executive Architecture Summary

`guitar-etl-pipeline v2.0` is a production-grade, multi-cloud **Autonomous Data & Decision Platform** bridging **Data Engineering**, **LLMOps**, and **Site Reliability Engineering (SRE)**:

1. **Resilient Multi-Cloud Extraction & LLM Entity Parsing ([`Program.cs`](Program.cs), [`ResiliencePipelineFactory.cs`](Services/ResiliencePipelineFactory.cs))**:
   Extracts unstructured luthier history from the **MediaWiki API** and secondary-market listings from the **Reverb Developer Hub API**. All external HTTP calls are governed by **Polly v8** resilience pipelines featuring exponential backoff with jitter, HTTP `429 TooManyRequests` handling, and circuit breakers. Unstructured text is coerced into strict JSON schemas via a routed **LiteLLM Proxy** ([`config/litellm_config.yaml`](config/litellm_config.yaml)).
2. **Event-Driven SRE Self-Healing & Dead-Letter Queue ([`SreRemediationService.cs`](Services/SreRemediationService.cs))**:
   Applies production SRE auto-remediation patterns directly to ELT pipelines prior to warehouse load. Inspects raw payloads for currency schema drift (e.g., `"$925.00 USD"` strings), inverted price bounds, duplicate entity chunks, and counterfeit/negative price anomalies—autonomously healing recoverable drift, routing poisoned payloads to a Dead-Letter Queue (`sre_quarantine_dlq.jsonl` / [`quarantine_dlq.sql`](guitar_analytics/models/quarantine_dlq.sql)), and emitting structured `INC-SRE-*` incident records.
3. **Dimensional Star Schema & Automated `dbt` Quality Gates ([`guitar_analytics/`](guitar_analytics/))**:
   Stages verified JSONL snapshots to **Google Cloud Storage** and transactional **Azure SQL**, then transforms them in **Google BigQuery** via `dbt` into [`dim_guitars`](guitar_analytics/models/dim_guitars.sql), [`fact_market_pricing`](guitar_analytics/models/fact_market_pricing.sql), and [`mart_instrument_valuation`](guitar_analytics/models/marts/mart_instrument_valuation.sql) with automated schema contracts ([`schema.yml`](guitar_analytics/models/schema.yml)).
4. **Autonomous Semantic Kernel Agent & Arbitrage Engine ([`GuitarAgent/`](GuitarAgent/))**:
   An interactive **Microsoft Semantic Kernel** agent ([`GuitarAgent.Console/Program.cs`](GuitarAgent/src/GuitarAgent.Console/Program.cs)) equipped with `FunctionChoiceBehavior.Auto()`, **OpenTelemetry** distributed tracing (`ActivityListener`), and [`GuitarDataPlugin`](GuitarAgent/src/GuitarAgent.AI/Plugins/GuitarDataPlugin.cs). Autonomously normalizes vintage/Norlin/modern eras ([`EraNormalizer.cs`](GuitarAgent/src/GuitarAgent.Domain/Services/EraNormalizer.cs)), queries live BigQuery comps ([`BigQueryRepository.cs`](GuitarAgent/src/GuitarAgent.Infrastructure/BigQuery/BigQueryRepository.cs)), and computes fee-adjusted resale ROI ([`ArbitrageCalculator.cs`](GuitarAgent/src/GuitarAgent.Domain/Services/ArbitrageCalculator.cs)).

---

## 2. System Architecture & Data Flow

```mermaid
flowchart LR
    subgraph Sources["External Data Sources"]
        Wiki["MediaWiki API<br/>(Historical Specs)"]
        Reverb["Reverb API<br/>(Live Market Comps)"]
    end

    subgraph ELT["C# .NET ELT & SRE Layer"]
        Polly["Polly v8 Resilience<br/>(Retry + Jitter + Circuit Breaker)"]
        LiteLLM["LiteLLM Router<br/>(JSON Schema Extraction)"]
        SRE["SreRemediationService<br/>(Drift Coercion & Anomaly Gate)"]
        DLQ[("Dead-Letter Queue<br/>sre_quarantine_dlq.jsonl")]
    end

    subgraph Storage["Multi-Cloud Persistence & dbt"]
        AzSQL[("Azure SQL DB<br/>(Operational Store)")]
        GCS[("Google Cloud Storage<br/>(JSONL Landing Zone)")]
        BQ[("Google BigQuery<br/>dim_guitars / fact_market_pricing /<br/>mart_instrument_valuation")]
    end

    subgraph Agentic["Semantic Kernel Agent (GuitarAgent)"]
        SK["Semantic Kernel Host<br/>(FunctionChoiceBehavior.Auto + OTel)"]
        Plugin["GuitarDataPlugin<br/>• NormalizeGuitarEra<br/>• GetMarketStatsAsync<br/>• EvaluateArbitrageOpportunityAsync"]
    end

    Wiki & Reverb --> Polly --> LiteLLM --> SRE
    SRE -- "Poisoned Payloads (INC-SRE-*)" --> DLQ
    SRE -- "Verified Clean Models" --> AzSQL & GCS
    GCS --> BQ
    BQ <--> Plugin <--> SK
