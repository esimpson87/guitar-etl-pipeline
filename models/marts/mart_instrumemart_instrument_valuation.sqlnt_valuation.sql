{{ config(materialized='table', tags=['star_schema', 'market_intelligence']) }}

WITH sold_comps AS (
      SELECT
          f.listing_id,
          f.instrument_key,
          f.price_usd,
          f.landed_cost_usd,
          f.listed_date
      FROM {{ ref('fact_market_listings') }} f
      WHERE f.listing_type = 'SOLD_COMP'
        AND f.price_usd > 0
  )
SELECT
    i.instrument_key,
    i.canonical_model,
    i.brand,
    i.pickup_config,
    i.country_of_origin,
    i.scale_length_in,
    COUNT(s.listing_id) AS sold_comp_count,
    ROUND(AVG(s.price_usd), 2) AS avg_sold_price_usd,
    ROUND(MIN(s.price_usd), 2) AS min_sold_price_usd,
    ROUND(MAX(s.price_usd), 2) AS max_sold_price_usd,
    ROUND(AVG(s.landed_cost_usd), 2) AS avg_landed_sold_usd
FROM {{ ref('dim_instrument') }} i
INNER JOIN sold_comps s
    ON i.instrument_key = s.instrument_key
GROUP BY
    i.instrument_key,
    i.canonical_model,
    i.brand,
    i.pickup_config,
    i.country_of_origin,
    i.scale_length_in
