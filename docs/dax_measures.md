# DAX measures

All measures live in `fact_sales` in the TMDL semantic model ([source](../powerbi/SalesIntelligence.SemanticModel/definition/tables/fact_sales.tmdl)). Expected values for validation are in [`reports/expected_measure_values.md`](../reports/expected_measure_values.md).

## Sales

### Total Revenue
Net revenue after discounts, excluding returned lines.

```dax
Total Revenue =
CALCULATE ( SUM ( fact_sales[net_revenue] ), fact_sales[is_returned] = FALSE () )
```
Format: `₹ #,0`

### Total Cost
Cost of goods for non-returned lines.

```dax
Total Cost =
CALCULATE ( SUM ( fact_sales[cost] ), fact_sales[is_returned] = FALSE () )
```
Format: `₹ #,0`

### Orders
Distinct orders with at least one kept line.

```dax
Orders =
CALCULATE ( DISTINCTCOUNT ( fact_sales[order_id] ), fact_sales[is_returned] = FALSE () )
```
Format: `#,0`

### Units Sold
Units on non-returned lines.

```dax
Units Sold =
CALCULATE ( SUM ( fact_sales[quantity] ), fact_sales[is_returned] = FALSE () )
```
Format: `#,0`

### Avg Order Value
Revenue per order.

```dax
Avg Order Value =
DIVIDE ( [Total Revenue], [Orders] )
```
Format: `₹ #,0`

### Return Rate %
Share of order lines returned.

```dax
Return Rate % =
DIVIDE (
    CALCULATE ( COUNTROWS ( fact_sales ), fact_sales[is_returned] = TRUE () ),
    COUNTROWS ( fact_sales )
)
```
Format: `0.00%`

## Profitability

### Gross Margin
Revenue minus cost.

```dax
Gross Margin =
[Total Revenue] - [Total Cost]
```
Format: `₹ #,0`

### Gross Margin %
Gross margin as a share of revenue.

```dax
Gross Margin % =
DIVIDE ( [Gross Margin], [Total Revenue] )
```
Format: `0.0%`

### Discount %
Discount as a share of gross (list) sales.

```dax
Discount % =
DIVIDE ( SUM ( fact_sales[discount_amount] ), SUM ( fact_sales[discount_amount] ) + SUM ( fact_sales[net_revenue] ) )
```
Format: `0.0%`

## Customers

### Active Customers
Customers who bought in the selected period.

```dax
Active Customers =
CALCULATE ( DISTINCTCOUNT ( fact_sales[customer_key] ), fact_sales[is_returned] = FALSE () )
```
Format: `#,0`

### New Customers
Customers whose first-ever purchase falls in the selected period.

```dax
New Customers =
VAR _start = MIN ( dim_date[date] )
VAR _end = MAX ( dim_date[date] )
RETURN
    COUNTROWS (
        FILTER (
            VALUES ( fact_sales[customer_key] ),
            VAR _first = CALCULATE ( MIN ( dim_date[date] ), REMOVEFILTERS ( dim_date ) )
            RETURN _first >= _start && _first <= _end
        )
    )
```
Format: `#,0`

### Revenue per Customer
Average revenue per buying customer.

```dax
Revenue per Customer =
DIVIDE ( [Total Revenue], [Active Customers] )
```
Format: `₹ #,0`

## Time Intelligence

### Revenue PY
Revenue in the same period last year.

```dax
Revenue PY =
CALCULATE ( [Total Revenue], SAMEPERIODLASTYEAR ( dim_date[date] ) )
```
Format: `₹ #,0`

### Revenue YoY %
Year-over-year growth; blank when there is no prior-year data.

```dax
Revenue YoY % =
VAR _cur = [Total Revenue]
VAR _py = [Revenue PY]
RETURN
    IF ( NOT ISBLANK ( _py ), DIVIDE ( _cur - _py, _py ) )
```
Format: `+0.0%;-0.0%;0.0%`

### Revenue PM
Revenue in the previous month.

```dax
Revenue PM =
CALCULATE ( [Total Revenue], DATEADD ( dim_date[date], -1, MONTH ) )
```
Format: `₹ #,0`

### Revenue MoM %
Month-over-month growth.

```dax
Revenue MoM % =
DIVIDE ( [Total Revenue] - [Revenue PM], [Revenue PM] )
```
Format: `+0.0%;-0.0%;0.0%`

### Revenue MTD
Month to date.

```dax
Revenue MTD =
TOTALMTD ( [Total Revenue], dim_date[date] )
```
Format: `₹ #,0`

### Revenue QTD
Quarter to date.

```dax
Revenue QTD =
TOTALQTD ( [Total Revenue], dim_date[date] )
```
Format: `₹ #,0`

### Revenue YTD
Calendar year to date.

```dax
Revenue YTD =
TOTALYTD ( [Total Revenue], dim_date[date] )
```
Format: `₹ #,0`

### Revenue FYTD
Indian financial year to date (April-March).

```dax
Revenue FYTD =
TOTALYTD ( [Total Revenue], dim_date[date], "31/3" )
```
Format: `₹ #,0`

### Revenue Running Total
Cumulative revenue from the first date up to the current context.

```dax
Revenue Running Total =
VAR _maxDate = MAX ( dim_date[date] )
RETURN
    CALCULATE ( [Total Revenue], dim_date[date] <= _maxDate, REMOVEFILTERS ( dim_date ) )
```
Format: `₹ #,0`

### Revenue 3M Rolling Avg
Average monthly revenue over the last 3 months.

```dax
Revenue 3M Rolling Avg =
VAR _months =
    DATESINPERIOD ( dim_date[date], MAX ( dim_date[date] ), -3, MONTH )
RETURN
    DIVIDE ( CALCULATE ( [Total Revenue], _months ), 3 )
```
Format: `₹ #,0`

## Ranking

### Category Rank
Rank of the category by revenue, respecting other filters.

```dax
Category Rank =
IF (
    HASONEVALUE ( dim_product[category] ),
    RANKX ( ALL ( dim_product[category] ), [Total Revenue],, DESC, DENSE )
)
```
Format: `0`

### City Rank
Rank of the city within the current selection.

```dax
City Rank =
IF (
    HASONEVALUE ( dim_store[city] ),
    RANKX ( ALLSELECTED ( dim_store[city] ), [Total Revenue],, DESC, DENSE )
)
```
Format: `0`

### Top N Revenue
Revenue shown only for the top N categories (N from the what-if slicer).

```dax
Top N Revenue =
VAR _n = SELECTEDVALUE ( 'Top N'[Top N], 5 )
RETURN
    IF ( [Category Rank] <= _n, [Total Revenue] )
```
Format: `₹ #,0`

### Revenue Share of Parent
Share of the level above in the Country > State > City > Store drill-down.

```dax
Revenue Share of Parent =
VAR _all =
    SWITCH (
        TRUE (),
        ISINSCOPE ( dim_store[store_name] ), CALCULATE ( [Total Revenue], ALLSELECTED ( dim_store[store_name] ) ),
        ISINSCOPE ( dim_store[city] ), CALCULATE ( [Total Revenue], ALLSELECTED ( dim_store[city] ) ),
        ISINSCOPE ( dim_store[state] ), CALCULATE ( [Total Revenue], ALLSELECTED ( dim_store[state] ) ),
        CALCULATE ( [Total Revenue], ALLSELECTED ( dim_store[country] ) )
    )
RETURN
    DIVIDE ( [Total Revenue], _all )
```
Format: `0.0%`

## Calculation group: Time Intelligence

Items: Current, PY, YoY, YoY %, MTD, QTD, YTD, FYTD (April-March). Apply to any measure instead of writing a PY/YTD version of each one. See [`Time Intelligence.tmdl`](../powerbi/SalesIntelligence.SemanticModel/definition/tables/Time%20Intelligence.tmdl).

## Row-level security

| Role | Rule |
|---|---|
| Country Manager (dynamic) | `dim_store[country] IN CALCULATETABLE(VALUES(security_user_country[country]), security_user_country[user_email] = USERPRINCIPALNAME())` |
| India Only (static) | `dim_store[country] = "India"` |
