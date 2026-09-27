-- Each query returns one row: check name, failing row count. 0 = pass.
SELECT
    'fact rows = staging rows' AS check_name,
    ABS((SELECT COUNT(*) FROM fact_sales) - (SELECT COUNT(*) FROM stg_order_lines)) AS failures
UNION ALL
SELECT
    'orphan date keys' AS check_name,
    COUNT(*) AS failures
FROM fact_sales AS f
LEFT JOIN dim_date AS d ON f.date_key = d.date_key
WHERE d.date_key IS NULL
UNION ALL
SELECT
    'duplicate customer keys' AS check_name,
    COUNT(*) - COUNT(DISTINCT customer_key) AS failures
FROM dim_customer
UNION ALL
SELECT
    'negative revenue' AS check_name,
    COUNT(*) AS failures
FROM fact_sales
WHERE net_revenue < 0
UNION ALL
SELECT
    'revenue reconciles to staging (paise)' AS check_name,
    CAST(ABS(
        (SELECT SUM(net_revenue) FROM fact_sales)
        - (SELECT SUM(ROUND(quantity * unit_price * (1 - discount_pct), 2)) FROM stg_order_lines)
    ) * 100 AS BIGINT) AS failures;
