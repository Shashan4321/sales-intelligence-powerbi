-- Fact table at order-line grain. Measures are stored pre-computed and additive.
CREATE OR REPLACE TABLE fact_sales AS
SELECT
    s.order_id,
    c.customer_key,
    st.store_key,
    p.product_key,
    s.channel,
    s.quantity,
    s.unit_price,
    s.discount_pct,
    s.is_returned,
    CAST(STRFTIME(s.order_date, '%Y%m%d') AS INTEGER) AS date_key,
    ROUND(s.quantity * s.unit_price * (1 - s.discount_pct), 2) AS net_revenue,
    ROUND(s.quantity * s.unit_price * s.discount_pct, 2) AS discount_amount,
    ROUND(s.quantity * s.unit_cost, 2) AS cost
FROM stg_order_lines AS s
INNER JOIN dim_customer AS c ON s.customer_id = c.customer_id
INNER JOIN dim_store AS st ON s.store_name = st.store_name
INNER JOIN dim_product AS p ON s.sku = p.sku;
