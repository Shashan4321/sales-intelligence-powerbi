-- Dimensions with integer surrogate keys (stable ordering => reproducible keys).

CREATE OR REPLACE TABLE dim_date AS
WITH bounds AS (
    SELECT
        DATE_TRUNC('year', MIN(order_date)) AS d0,
        MAKE_DATE(YEAR(MAX(order_date)), 12, 31) AS d1
    FROM stg_order_lines
)

SELECT
    CAST(STRFTIME(d.date_day, '%Y%m%d') AS INTEGER) AS date_key,
    CAST(d.date_day AS DATE) AS date,
    YEAR(d.date_day) AS year,
    QUARTER(d.date_day) AS quarter,
    MONTH(d.date_day) AS month,
    STRFTIME(d.date_day, '%b') AS month_name,
    STRFTIME(d.date_day, '%Y-%m') AS year_month,
    DAYOFWEEK(d.date_day) IN (0, 6) AS is_weekend,
    -- Indian financial year (April-March): FY2025 = Apr-2024..Mar-2025
    CASE
        WHEN MONTH(d.date_day) >= 4 THEN YEAR(d.date_day) + 1
        ELSE YEAR(d.date_day)
    END AS fiscal_year
FROM bounds AS b,
    GENERATE_SERIES(b.d0, b.d1, INTERVAL 1 DAY) AS d (date_day);

CREATE OR REPLACE TABLE dim_customer AS
SELECT
    customer_id,
    ANY_VALUE(segment) AS segment,
    MIN(signup_date) AS signup_date,
    ROW_NUMBER() OVER (ORDER BY customer_id) AS customer_key
FROM stg_order_lines
GROUP BY customer_id;

CREATE OR REPLACE TABLE dim_store AS
SELECT
    store_name,
    city,
    state,
    country,
    CASE WHEN country = 'India' THEN 'Domestic' ELSE 'International' END AS region,
    ROW_NUMBER() OVER (ORDER BY country, state, city, store_name) AS store_key
FROM (SELECT DISTINCT
    store_name,
    city,
    state,
    country
FROM stg_order_lines) AS s;

CREATE OR REPLACE TABLE dim_product AS
SELECT
    sku,
    product_name,
    category,
    subcategory,
    brand,
    list_price,
    ROW_NUMBER() OVER (ORDER BY sku) AS product_key
FROM (
    SELECT
        sku,
        ANY_VALUE(product_name) AS product_name,
        ANY_VALUE(category) AS category,
        ANY_VALUE(subcategory) AS subcategory,
        ANY_VALUE(brand) AS brand,
        MAX(unit_price) AS list_price
    FROM stg_order_lines
    GROUP BY sku
) AS p;
