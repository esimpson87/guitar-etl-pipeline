# Multi-Cloud Guitar Market ETL Pipeline

## Overview
This repository contains a production-grade ETL/ELT pipeline that extracts electric guitar specifications from unstructured text, enriches them with live secondary market pricing, and orchestrates the data across Azure and Google Cloud infrastructure. 
Designed to support business intelligence and pricing analytics, the architecture demonstrates cross-cloud integration, AI-driven data parsing, and robust error handling suited for Senior Data Engineering and Site Reliability Engineering standards.

## Architecture & Tech Stack

* **Application Logic:** C# (.NET 8)
* **Data Sources:** MediaWiki API, Reverb Developer Hub API
* **AI Processing:** Local LiteLLM proxy (coercing unstructured text into strict JSON schemas)
* **Operational Storage:** Azure SQL Database
* **Data Lake:** Google Cloud Storage (JSONL landing zone)
* **Data Warehouse:** Google BigQuery (Schema-on-read external tables)
* **Transformations:** dbt (Data Build Tool)

## Pipeline Workflow

1. **Extract:** The C# application pulls unstructured historical text from Wikipedia and authenticates with a personal access token to fetch live secondary market data from the Reverb API.
2. **AI Transformation:** A local LiteLLM proxy parses the unstructured text, extracting specific hardware traits (pickups, finishes, body construction) into a strict JSON payload.
3. **Operational Load:** The raw extraction is inserted into an Azure SQL database for transactional application use, utilizing parameterized queries to prevent injection.
4. **Data Lake Staging:** The payload is serialized into JSON Lines (`.jsonl`) and uploaded to a Google Cloud Storage bucket.
5. **Analytical Transformation:** BigQuery reads the GCS bucket as an external table. A dbt project then flattens the nested JSON arrays and casts types to build a production-ready star schema (`dim_guitars` and `fact_market_pricing`).

## Engineering Challenges Solved

* **API Rate Limiting:** Implemented asynchronous concurrency controls and artificial delays to respect third-party API throttling constraints without crashing the pipeline.
* **Security & Configuration:** Abstracted all database connection strings, cloud keys, and API tokens out of the codebase using environment variables (`.env`) and `.gitignore` policies.
* **Idempotent Infrastructure:** Engineered the C# application to automatically verify and provision required SQL schemas on startup if they do not exist.
* **Cross-Cloud IAM:** Configured distinct Google Cloud Service Accounts with scoped permissions (Storage Object Admin, BigQuery Data Editor, BigQuery Job User) to ensure the principle of least privilege between the extraction application and the dbt transformation layer.

## Business Intelligence Visualization
An interactive Looker Studio dashboard connected directly to the BigQuery analytical dataset allows users to filter and explore Reverb pricing trends against historical production configurations.

[View the Dashboard](https://datastudio.google.com/reporting/888d714c-88e8-43d7-9555-a9a57f213e9a)
