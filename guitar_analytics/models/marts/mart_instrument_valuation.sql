{{ config(materialized='table', tags=['star_schema', 'market_intelligence']) }}

WITH valid_pricing AS (
    SELECT
        f.guitar_model,
        f.average_price,
        f.lowest_price,
        f.listing_count,
        f.snapshot_timestamp
    FROM {{ ref('fact_market_pricing') }} f
    WHERE f.average_price > 0
      AND f.listing_count > 0
)
SELECT
    d.guitar_model AS canonical_model,
    d.production_years,
    d.body_construction,
    d.pickups_list AS pickup_config,
    d.finishes_list AS notable_finishes,
    COUNT(p.snapshot_timestamp) AS snapshot_count,
    SUM(p.listing_count) AS total_listings_observed,
    ROUND(AVG(p.average_price), 2) AS avg_market_price_usd,
    ROUND(MIN(p.lowest_price), 2) AS min_observed_price_usd,
    ROUND(MAX(p.average_price), 2) AS max_observed_avg_usd,
    MAX(p.snapshot_timestamp) AS last_updated_at
FROM {{ ref('dim_guitars') }} d
INNER JOIN valid_pricing p
    ON TRIM(LOWER(d.guitar_model)) = TRIM(LOWER(p.guitar_model))
GROUP BY
    d.guitar_model,
    d.production_years,
    d.body_construction,
    d.pickups_list,
    d.finishes_list
