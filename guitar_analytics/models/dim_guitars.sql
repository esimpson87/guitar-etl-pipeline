{{ config(materialized='table') }}

SELECT DISTINCT
    Model.model_name AS guitar_model,
    Model.production_years,
    Model.body_construction,
    ARRAY_TO_STRING(Model.pickups, ', ') AS pickups_list,
    ARRAY_TO_STRING(Model.notable_finishes, ', ') AS finishes_list
FROM `guitaretl-analytics.raw_landing.market_snapshots`
WHERE Model.model_name IS NOT NULL