-- Staging: load the raw extract as-is, fix types, trim text.
CREATE OR REPLACE TABLE stg_order_lines AS
SELECT
    TRIM(order_id) AS order_id,
    CAST(order_date AS DATE) AS order_date,
    TRIM(customer_id) AS customer_id,
    TRIM(segment) AS segment,
    CAST(signup_date AS DATE) AS signup_date,
    TRIM(store_name) AS store_name,
    TRIM(city) AS city,
    TRIM(state) AS state,
    TRIM(country) AS country,
    TRIM(channel) AS channel,
    TRIM(sku) AS sku,
    TRIM(product_name) AS product_name,
    TRIM(category) AS category,
    TRIM(subcategory) AS subcategory,
    TRIM(brand) AS brand,
    CAST(quantity AS INTEGER) AS quantity,
    CAST(unit_price AS DECIMAL(12, 2)) AS unit_price,
    CAST(discount_pct AS DECIMAL(5, 4)) AS discount_pct,
    CAST(unit_cost AS DECIMAL(12, 2)) AS unit_cost,
    CAST(is_returned AS BOOLEAN) AS is_returned
FROM READ_CSV_AUTO(GETVARIABLE('raw_path'), header = TRUE);
