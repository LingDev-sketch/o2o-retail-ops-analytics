-- O2O即时零售运营分析 SQL 示例
-- 适合在面试中说明：多表关联、窗口函数、CTE、异常门店识别、促销复盘。

-- 1. 城市维度经营指标
SELECT
    o.city,
    COUNT(DISTINCT o.order_id) AS order_count,
    ROUND(SUM(o.gmv), 2) AS gmv,
    ROUND(SUM(o.gmv) / NULLIF(COUNT(DISTINCT o.order_id), 0), 2) AS aov,
    ROUND(SUM(o.refund_flag) / NULLIF(COUNT(DISTINCT o.order_id), 0), 4) AS refund_rate
FROM orders o
WHERE o.date BETWEEN '2026-06-01' AND '2026-06-30'
GROUP BY o.city
ORDER BY gmv DESC;

-- 2. 使用窗口函数识别 GMV 低于近 7 日均值 30% 的门店
WITH store_daily AS (
    SELECT
        store_id,
        date,
        SUM(gmv) AS gmv,
        COUNT(DISTINCT order_id) AS order_count
    FROM orders
    GROUP BY store_id, date
),
rolling_base AS (
    SELECT
        store_id,
        date,
        gmv,
        order_count,
        AVG(gmv) OVER (
            PARTITION BY store_id
            ORDER BY date
            ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
        ) AS gmv_7d_avg
    FROM store_daily
)
SELECT
    store_id,
    date,
    gmv,
    gmv_7d_avg,
    ROUND(gmv / NULLIF(gmv_7d_avg, 0) - 1, 4) AS gmv_drop_rate
FROM rolling_base
WHERE gmv_7d_avg > 0
  AND gmv / gmv_7d_avg - 1 <= -0.30
ORDER BY date DESC, gmv_drop_rate ASC;

-- 3. 高销量低库存 SKU 识别
WITH product_sales AS (
    SELECT
        product_id,
        SUM(quantity) AS sales_qty,
        SUM(gmv) AS gmv
    FROM orders
    WHERE date BETWEEN '2026-06-01' AND '2026-06-30'
    GROUP BY product_id
),
product_stock AS (
    SELECT
        product_id,
        AVG(stock_qty) AS avg_stock,
        SUM(CASE WHEN stock_qty < safety_stock THEN 1 ELSE 0 END) AS low_stock_days
    FROM inventory
    WHERE date BETWEEN '2026-06-01' AND '2026-06-30'
    GROUP BY product_id
)
SELECT
    p.product_id,
    p.product_name,
    p.category,
    s.sales_qty,
    s.gmv,
    i.avg_stock,
    i.low_stock_days
FROM product_sales s
JOIN product_stock i ON s.product_id = i.product_id
JOIN products p ON s.product_id = p.product_id
WHERE s.sales_qty >= 500
  AND i.avg_stock <= 18
ORDER BY s.gmv DESC;

-- 4. 促销前后 7 天 GMV uplift
WITH promo_product AS (
    SELECT
        promotion_id,
        product_id,
        start_date,
        end_date
    FROM promotions
),
promo_effect AS (
    SELECT
        p.promotion_id,
        p.product_id,
        SUM(CASE
            WHEN o.date BETWEEN DATE_SUB(p.start_date, INTERVAL 7 DAY) AND DATE_SUB(p.start_date, INTERVAL 1 DAY)
            THEN o.gmv ELSE 0 END) AS pre_7d_gmv,
        SUM(CASE
            WHEN o.date BETWEEN p.start_date AND p.end_date
            THEN o.gmv ELSE 0 END) AS promo_7d_gmv
    FROM promo_product p
    LEFT JOIN orders o ON p.product_id = o.product_id
    GROUP BY p.promotion_id, p.product_id
)
SELECT
    promotion_id,
    product_id,
    pre_7d_gmv,
    promo_7d_gmv,
    ROUND(promo_7d_gmv / NULLIF(pre_7d_gmv, 0) - 1, 4) AS promo_lift
FROM promo_effect
ORDER BY promo_lift DESC;
