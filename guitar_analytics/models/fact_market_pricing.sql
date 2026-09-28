{{ config(materialized='table') }}

SELECT
    Model.model_name AS guitar_model,
    CAST(Model.average_price_usd AS NUMERIC) AS average_price,
    CAST(Model.lowest_price_usd AS NUMERIC) AS lowest_price,
    CAST(Model.listing_count AS INT64) AS listing_count,
    CAST(ExtractedAt AS TIMESTAMP) AS snapshot_timestamp
FROM `guitaretl-analytics.raw_landing.market_snapshots`
WHERE Model.model_name IS NOT NULL