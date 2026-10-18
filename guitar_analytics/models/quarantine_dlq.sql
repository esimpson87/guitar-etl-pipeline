{{ config(materialized='view', tags=['sre', 'dlq']) }}

SELECT
    incident_id,
    raw_model_name,
    anomaly_type,
    remediation_status,
    raw_average_price,
    raw_lowest_price,
    raw_listing_count,
    failure_reason,
    quarantined_at
FROM `guitaretl-analytics.raw_landing.sre_quarantine_dlq`
WHERE remediation_status = 'QUARANTINED'
