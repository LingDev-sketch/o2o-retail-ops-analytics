from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RULES_PATH = ROOT / "config" / "rules.yaml"


st.set_page_config(
    page_title="O2O即时零售运营分析工具",
    page_icon="📊",
    layout="wide",
)


@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    orders = pd.read_csv(DATA_DIR / "orders.csv", parse_dates=["date"])
    stores = pd.read_csv(DATA_DIR / "stores.csv", parse_dates=["open_date"])
    products = pd.read_csv(DATA_DIR / "products.csv")
    inventory = pd.read_csv(DATA_DIR / "inventory.csv", parse_dates=["date"])
    promotions = pd.read_csv(DATA_DIR / "promotions.csv", parse_dates=["start_date", "end_date"])
    rules = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
    return orders, stores, products, inventory, promotions, rules


def pct_text(value: float) -> str:
    return f"{value:.1%}"


def money_text(value: float) -> str:
    return f"{value / 10000:.1f}万"


def filter_data(
    orders: pd.DataFrame,
    inventory: pd.DataFrame,
    stores: pd.DataFrame,
    date_range: tuple[pd.Timestamp, pd.Timestamp],
    cities: list[str],
    categories: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    start, end = date_range
    store_ids = stores.loc[stores["city"].isin(cities), "store_id"]
    order_filtered = orders[
        (orders["date"].between(start, end))
        & (orders["city"].isin(cities))
        & (orders["category"].isin(categories))
    ].copy()
    inventory_filtered = inventory[
        (inventory["date"].between(start, end)) & (inventory["store_id"].isin(store_ids))
    ].copy()
    return order_filtered, inventory_filtered


def daily_metrics(orders: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    order_daily = (
        orders.groupby("date", as_index=False)
        .agg(
            gmv=("gmv", "sum"),
            order_count=("order_id", "nunique"),
            promo_orders=("is_promo", "sum"),
            refund_orders=("refund_flag", "sum"),
        )
        .sort_values("date")
    )
    inv_daily = (
        inventory.assign(is_stockout=lambda d: d["stock_qty"] < d["safety_stock"])
        .groupby("date", as_index=False)
        .agg(stockout_rate=("is_stockout", "mean"))
    )
    metrics = order_daily.merge(inv_daily, on="date", how="left")
    metrics["aov"] = metrics["gmv"] / metrics["order_count"].replace(0, pd.NA)
    metrics["promo_order_rate"] = metrics["promo_orders"] / metrics["order_count"].replace(0, pd.NA)
    metrics["refund_rate"] = metrics["refund_orders"] / metrics["order_count"].replace(0, pd.NA)
    return metrics.fillna(0)


def store_metrics(orders: pd.DataFrame, inventory: pd.DataFrame, stores: pd.DataFrame) -> pd.DataFrame:
    order_store = (
        orders.groupby("store_id", as_index=False)
        .agg(
            gmv=("gmv", "sum"),
            order_count=("order_id", "nunique"),
            promo_orders=("is_promo", "sum"),
            refund_orders=("refund_flag", "sum"),
        )
    )
    inv_store = (
        inventory.assign(is_stockout=lambda d: d["stock_qty"] < d["safety_stock"])
        .groupby("store_id", as_index=False)
        .agg(stockout_rate=("is_stockout", "mean"))
    )
    metrics = stores.merge(order_store, on="store_id", how="left").merge(inv_store, on="store_id", how="left")
    metrics[["gmv", "order_count", "promo_orders", "refund_orders", "stockout_rate"]] = metrics[
        ["gmv", "order_count", "promo_orders", "refund_orders", "stockout_rate"]
    ].fillna(0)
    metrics["aov"] = metrics["gmv"] / metrics["order_count"].replace(0, pd.NA)
    metrics["refund_rate"] = metrics["refund_orders"] / metrics["order_count"].replace(0, pd.NA)
    metrics["promo_order_rate"] = metrics["promo_orders"] / metrics["order_count"].replace(0, pd.NA)
    return metrics.fillna(0)


def detect_anomalies(
    orders: pd.DataFrame,
    inventory: pd.DataFrame,
    stores: pd.DataFrame,
    rules: dict,
) -> pd.DataFrame:
    daily_store = (
        orders.groupby(["store_id", "date"], as_index=False)
        .agg(gmv=("gmv", "sum"), order_count=("order_id", "nunique"), refund_orders=("refund_flag", "sum"))
        .sort_values(["store_id", "date"])
    )
    daily_store["gmv_7d_avg"] = daily_store.groupby("store_id")["gmv"].transform(
        lambda s: s.shift(1).rolling(7, min_periods=3).mean()
    )
    daily_store["order_7d_avg"] = daily_store.groupby("store_id")["order_count"].transform(
        lambda s: s.shift(1).rolling(7, min_periods=3).mean()
    )
    daily_store["refund_rate"] = daily_store["refund_orders"] / daily_store["order_count"].replace(0, pd.NA)

    inv_store = (
        inventory.assign(is_stockout=lambda d: d["stock_qty"] < d["safety_stock"])
        .groupby(["store_id", "date"], as_index=False)
        .agg(stockout_rate=("is_stockout", "mean"))
    )
    daily_store = daily_store.merge(inv_store, on=["store_id", "date"], how="left").fillna(0)

    rows: list[dict] = []
    latest_days = daily_store["date"].sort_values().unique()[-10:]
    recent = daily_store[daily_store["date"].isin(latest_days)]
    for row in recent.itertuples(index=False):
        if row.gmv_7d_avg and row.gmv_7d_avg > 0:
            gmv_delta = row.gmv / row.gmv_7d_avg - 1
            if gmv_delta <= rules["gmv_drop_7d"]["threshold"]:
                rows.append(
                    {
                        "date": row.date,
                        "store_id": row.store_id,
                        "rule": "GMV连续下滑",
                        "level": rules["gmv_drop_7d"]["level"],
                        "metric_value": pct_text(gmv_delta),
                        "suggestion": rules["gmv_drop_7d"]["suggestion"],
                    }
                )
        if row.order_7d_avg and row.order_7d_avg > 0:
            order_delta = row.order_count / row.order_7d_avg - 1
            if order_delta <= rules["order_drop_7d"]["threshold"]:
                rows.append(
                    {
                        "date": row.date,
                        "store_id": row.store_id,
                        "rule": "订单量低于均值",
                        "level": rules["order_drop_7d"]["level"],
                        "metric_value": pct_text(order_delta),
                        "suggestion": rules["order_drop_7d"]["suggestion"],
                    }
                )
        if row.stockout_rate >= rules["stockout_rate_high"]["threshold"]:
            rows.append(
                {
                    "date": row.date,
                    "store_id": row.store_id,
                    "rule": "缺货率过高",
                    "level": rules["stockout_rate_high"]["level"],
                    "metric_value": pct_text(row.stockout_rate),
                    "suggestion": rules["stockout_rate_high"]["suggestion"],
                }
            )
        if row.refund_rate >= rules["refund_rate_high"]["threshold"]:
            rows.append(
                {
                    "date": row.date,
                    "store_id": row.store_id,
                    "rule": "退款率异常",
                    "level": rules["refund_rate_high"]["level"],
                    "metric_value": pct_text(row.refund_rate),
                    "suggestion": rules["refund_rate_high"]["suggestion"],
                }
            )

    anomalies = pd.DataFrame(rows)
    if anomalies.empty:
        return anomalies
    return anomalies.merge(stores[["store_id", "store_name", "city", "region"]], on="store_id", how="left")[
        ["date", "city", "region", "store_id", "store_name", "rule", "level", "metric_value", "suggestion"]
    ].sort_values(["date", "level"], ascending=[False, True])


def product_inventory_view(orders: pd.DataFrame, inventory: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    sales = (
        orders.groupby("product_id", as_index=False)
        .agg(gmv=("gmv", "sum"), quantity=("quantity", "sum"), order_count=("order_id", "nunique"))
    )
    stock = (
        inventory.groupby("product_id", as_index=False)
        .agg(avg_stock=("stock_qty", "mean"), low_stock_days=("stock_qty", lambda s: int((s < 15).sum())))
    )
    result = products.merge(sales, on="product_id", how="left").merge(stock, on="product_id", how="left").fillna(0)
    result["stock_risk"] = result.apply(
        lambda r: "高销量低库存" if r["quantity"] >= result["quantity"].quantile(0.75) and r["avg_stock"] <= 18 else "正常",
        axis=1,
    )
    return result.sort_values("gmv", ascending=False)


def promo_view(orders: pd.DataFrame, promotions: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for promo in promotions.itertuples(index=False):
        before_start = promo.start_date - pd.Timedelta(days=7)
        before_end = promo.start_date - pd.Timedelta(days=1)
        before = orders[
            (orders["product_id"] == promo.product_id)
            & (orders["date"].between(before_start, before_end))
        ]["gmv"].sum()
        during = orders[
            (orders["product_id"] == promo.product_id)
            & (orders["date"].between(promo.start_date, promo.end_date))
        ]["gmv"].sum()
        lift = during / before - 1 if before > 0 else 0
        rows.append(
            {
                "product_id": promo.product_id,
                "start_date": promo.start_date,
                "end_date": promo.end_date,
                "discount_rate": promo.discount_rate,
                "pre_7d_gmv": before,
                "promo_7d_gmv": during,
                "promo_lift": lift,
            }
        )
    return pd.DataFrame(rows).merge(products[["product_id", "product_name", "category"]], on="product_id", how="left")


orders, stores, products, inventory, promotions, rules = load_data()

st.title("O2O即时零售运营数据质量监控与自动化分析平台")
st.caption("模拟将运营同学依赖 Excel/Power Query 的日报、异常筛查和促销复盘流程迁移为 Python + Streamlit 工具。")

with st.sidebar:
    st.header("筛选条件")
    min_date = orders["date"].min().date()
    max_date = orders["date"].max().date()
    selected_dates = st.date_input("日期范围", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    if len(selected_dates) != 2:
        st.stop()
    selected_cities = st.multiselect("城市", sorted(orders["city"].unique()), default=sorted(orders["city"].unique()))
    selected_categories = st.multiselect(
        "品类", sorted(orders["category"].unique()), default=sorted(orders["category"].unique())
    )

start_date, end_date = pd.Timestamp(selected_dates[0]), pd.Timestamp(selected_dates[1])
orders_f, inventory_f = filter_data(
    orders,
    inventory,
    stores,
    (start_date, end_date),
    selected_cities,
    selected_categories,
)

daily = daily_metrics(orders_f, inventory_f)
store = store_metrics(orders_f, inventory_f, stores[stores["city"].isin(selected_cities)])

total_gmv = orders_f["gmv"].sum()
order_count = orders_f["order_id"].nunique()
aov = total_gmv / order_count if order_count else 0
refund_rate = orders_f["refund_flag"].sum() / order_count if order_count else 0
stockout_rate = (inventory_f["stock_qty"] < inventory_f["safety_stock"]).mean() if len(inventory_f) else 0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("GMV", money_text(total_gmv))
col2.metric("订单量", f"{order_count:,}")
col3.metric("客单价", f"{aov:.1f}")
col4.metric("退款率", pct_text(refund_rate))
col5.metric("缺货率", pct_text(stockout_rate))

tab1, tab2, tab3, tab4, tab5 = st.tabs(["经营看板", "异常门店", "商品库存", "促销复盘", "规则配置"])

with tab1:
    left, right = st.columns([1.4, 1])
    with left:
        fig = px.line(daily, x="date", y=["gmv", "order_count"], title="GMV 与订单量趋势")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        top_store = store.nlargest(10, "gmv")
        fig = px.bar(top_store, x="gmv", y="store_name", color="city", orientation="h", title="TOP10 门店 GMV")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)

    city_perf = (
        orders_f.groupby("city", as_index=False)
        .agg(gmv=("gmv", "sum"), order_count=("order_id", "nunique"), refund_orders=("refund_flag", "sum"))
        .assign(refund_rate=lambda d: d["refund_orders"] / d["order_count"].replace(0, pd.NA))
        .fillna(0)
        .sort_values("gmv", ascending=False)
    )
    st.dataframe(city_perf, use_container_width=True, hide_index=True)

with tab2:
    anomalies = detect_anomalies(orders_f, inventory_f, stores, rules)
    st.subheader("近 10 天异常门店清单")
    if anomalies.empty:
        st.success("当前筛选范围内未识别到异常门店。")
    else:
        st.dataframe(anomalies, use_container_width=True, hide_index=True)
        st.download_button(
            "下载异常清单 CSV",
            anomalies.to_csv(index=False, encoding="utf-8-sig"),
            file_name="store_anomalies.csv",
            mime="text/csv",
        )

with tab3:
    product_view = product_inventory_view(orders_f, inventory_f, products)
    left, right = st.columns([1, 1])
    with left:
        fig = px.bar(product_view.head(12), x="gmv", y="product_name", color="category", orientation="h", title="商品 GMV 排名")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)
    with right:
        risk_products = product_view[product_view["stock_risk"] == "高销量低库存"]
        st.subheader("高销量低库存商品")
        st.dataframe(
            risk_products[["product_id", "product_name", "category", "gmv", "quantity", "avg_stock", "low_stock_days"]],
            use_container_width=True,
            hide_index=True,
        )
    st.dataframe(product_view, use_container_width=True, hide_index=True)

with tab4:
    promo = promo_view(orders_f, promotions, products)
    promo["promo_lift_text"] = promo["promo_lift"].map(pct_text)
    fig = px.bar(promo, x="product_name", y="promo_lift", color="category", title="促销前后 GMV 提升率")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(promo, use_container_width=True, hide_index=True)

with tab5:
    st.subheader("YAML 异常规则配置")
    st.code(RULES_PATH.read_text(encoding="utf-8"), language="yaml")
    st.info("面试讲法：新增客户指标或异常规则时，优先调整配置文件，减少重复改代码。")
