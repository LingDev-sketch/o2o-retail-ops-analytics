from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RULES_PATH = ROOT / "config" / "rules.yaml"
SAMPLE_EXCEL = DATA_DIR / "sample_o2o_upload.xlsx"

REQUIRED_COLUMNS = {
    "orders": {"order_id", "date", "store_id", "product_id", "city", "category", "quantity", "gmv", "refund_flag", "is_promo"},
    "stores": {"store_id", "store_name", "city", "region", "store_type"},
    "products": {"product_id", "product_name", "brand", "category", "cost_price", "sale_price"},
    "inventory": {"date", "store_id", "product_id", "stock_qty", "safety_stock"},
    "promotions": {"promotion_id", "product_id", "start_date", "end_date", "discount_rate"},
}


st.set_page_config(
    page_title="Excel上传版-O2O即时零售运营分析工具",
    page_icon="📤",
    layout="wide",
)


def pct_text(value: float) -> str:
    return f"{value:.1%}"


def money_text(value: float) -> str:
    return f"{value / 10000:.1f}万"


def read_workbook(uploaded_file) -> dict[str, pd.DataFrame]:
    workbook = pd.ExcelFile(uploaded_file)
    sheet_map = {name.lower(): name for name in workbook.sheet_names}
    missing_sheets = [name for name in REQUIRED_COLUMNS if name not in sheet_map]
    if missing_sheets:
        raise ValueError(f"缺少工作表：{', '.join(missing_sheets)}")

    data: dict[str, pd.DataFrame] = {}
    for key in REQUIRED_COLUMNS:
        df = pd.read_excel(workbook, sheet_name=sheet_map[key])
        df.columns = [str(col).strip() for col in df.columns]
        missing_cols = sorted(REQUIRED_COLUMNS[key] - set(df.columns))
        if missing_cols:
            raise ValueError(f"{key} 工作表缺少字段：{', '.join(missing_cols)}")
        data[key] = df

    data["orders"]["date"] = pd.to_datetime(data["orders"]["date"])
    data["inventory"]["date"] = pd.to_datetime(data["inventory"]["date"])
    data["stores"]["open_date"] = pd.to_datetime(data["stores"].get("open_date"), errors="coerce")
    data["promotions"]["start_date"] = pd.to_datetime(data["promotions"]["start_date"])
    data["promotions"]["end_date"] = pd.to_datetime(data["promotions"]["end_date"])
    return data


@st.cache_data
def load_sample_data() -> dict[str, pd.DataFrame]:
    data = {
        "orders": pd.read_csv(DATA_DIR / "orders.csv", parse_dates=["date"]),
        "stores": pd.read_csv(DATA_DIR / "stores.csv", parse_dates=["open_date"]),
        "products": pd.read_csv(DATA_DIR / "products.csv"),
        "inventory": pd.read_csv(DATA_DIR / "inventory.csv", parse_dates=["date"]),
        "promotions": pd.read_csv(DATA_DIR / "promotions.csv", parse_dates=["start_date", "end_date"]),
    }
    return data


@st.cache_data
def load_rules() -> dict:
    return yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))


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


def build_ai_summary(
    total_gmv: float,
    order_count: int,
    aov: float,
    refund_rate: float,
    stockout_rate: float,
    daily: pd.DataFrame,
    store: pd.DataFrame,
    anomalies: pd.DataFrame,
    product_view: pd.DataFrame,
    promo: pd.DataFrame,
) -> list[str]:
    summary: list[str] = []
    if daily.empty or order_count == 0:
        return ["当前筛选范围内订单数据不足，建议扩大日期、城市或品类范围后重新查看。"]

    first_gmv = daily.iloc[0]["gmv"]
    last_gmv = daily.iloc[-1]["gmv"]
    gmv_change = last_gmv / first_gmv - 1 if first_gmv else 0
    first_orders = daily.iloc[0]["order_count"]
    last_orders = daily.iloc[-1]["order_count"]
    order_change = last_orders / first_orders - 1 if first_orders else 0

    top_city = "暂无"
    if not store.empty:
        top_city = store.groupby("city", as_index=False)["gmv"].sum().sort_values("gmv", ascending=False).iloc[0]["city"]

    summary.append(
        f"经营概览：当前筛选范围内 GMV 为 {money_text(total_gmv)}，订单量 {order_count:,} 单，"
        f"客单价 {aov:.1f} 元；GMV 较首日变化 {pct_text(gmv_change)}，订单量较首日变化 {pct_text(order_change)}。"
    )
    if gmv_change < -0.15 and order_change < -0.1:
        summary.append("销售趋势：GMV 与订单量同步下滑，优先排查流量曝光、门店营业状态、活动结束或履约异常。")
    elif gmv_change < -0.15:
        summary.append("销售趋势：GMV 下滑较明显，但订单量未同步大幅下降，建议重点关注客单价、商品结构和促销折扣变化。")
    elif gmv_change > 0.15:
        summary.append(f"销售趋势：GMV 增长较明显，主要贡献城市可优先关注 {top_city}，建议复盘高表现门店和品类。")
    else:
        summary.append("销售趋势：GMV 整体波动处于相对可控范围，建议继续关注异常门店和库存风险。")

    if anomalies.empty:
        summary.append("异常监控：近 10 天未识别到明显异常门店，当前经营风险相对平稳。")
    else:
        rule_counts = anomalies["rule"].value_counts().head(3)
        rule_text = "、".join([f"{rule} {count} 次" for rule, count in rule_counts.items()])
        high_count = int((anomalies["level"] == "high").sum())
        summary.append(
            f"异常监控：近 10 天共识别 {len(anomalies)} 条异常记录，其中 high 等级 {high_count} 条；"
            f"主要异常类型为 {rule_text}。"
        )

    if stockout_rate >= 0.15:
        summary.append(f"库存风险：整体缺货率为 {pct_text(stockout_rate)}，已超过 15% 预警线，建议优先检查热销 SKU 补货和安全库存设置。")
    elif stockout_rate >= 0.08:
        summary.append(f"库存风险：整体缺货率为 {pct_text(stockout_rate)}，处于需要关注区间，建议跟踪高销量低库存商品。")
    else:
        summary.append(f"库存风险：整体缺货率为 {pct_text(stockout_rate)}，库存风险暂时较低。")

    risk_products = product_view[product_view["stock_risk"] == "高销量低库存"] if not product_view.empty else pd.DataFrame()
    if not risk_products.empty:
        top_risk = risk_products.sort_values("gmv", ascending=False).iloc[0]
        summary.append(
            f"商品建议：识别到 {len(risk_products)} 个高销量低库存商品，优先关注 "
            f"{top_risk['product_name']}，避免库存不足影响销售承接。"
        )

    if not promo.empty:
        avg_lift = promo["promo_lift"].mean()
        best_promo = promo.sort_values("promo_lift", ascending=False).iloc[0]
        if avg_lift > 0.2:
            promo_judgement = "促销整体拉动效果较好"
        elif avg_lift > 0:
            promo_judgement = "促销整体有一定拉动，但效果一般"
        else:
            promo_judgement = "促销整体拉动不足"
        summary.append(
            f"促销复盘：平均促销 uplift 为 {pct_text(avg_lift)}，{promo_judgement}；"
            f"其中 {best_promo['product_name']} 提升率最高，为 {pct_text(best_promo['promo_lift'])}。"
        )

    if refund_rate >= 0.08:
        summary.append(f"履约质量：退款率为 {pct_text(refund_rate)}，超过 8% 预警线，建议按门店、商品和日期拆解退款原因。")
    else:
        summary.append(f"履约质量：退款率为 {pct_text(refund_rate)}，当前整体退款风险可控。")

    summary.append("行动建议：优先跟进 high 等级异常门店、高销量低库存商品，以及促销 uplift 较低但缺货率较高的商品。")
    return summary


def render_pygwalker_explorer(df: pd.DataFrame) -> None:
    try:
        import pygwalker as pyg
        import streamlit.components.v1 as components
    except ImportError as exc:
        st.warning(f"PyGWalker 依赖未就绪：{exc}。请确认 requirements.txt 中包含 pygwalker。")
        return

    if df.empty:
        st.info("当前筛选条件下没有可探索的数据。")
        return

    max_rows = 2000
    if len(df) > max_rows:
        st.info(f"当前数据量较大，已取前 {max_rows:,} 行用于自助探索，避免页面加载过慢。")
        df = df.head(max_rows)

    try:
        html = pyg.to_html(df)
        components.html(html, height=760, scrolling=True)
    except Exception as exc:
        st.error(f"PyGWalker 渲染失败：{exc}")


st.title("Excel上传版-O2O即时零售运营数据质量监控与自动化分析平台")
st.caption("上传 ERP、订单系统、库存系统导出的 Excel 工作簿，自动完成指标监控、异常识别、促销复盘和分析总结。")

with st.expander("Excel 工作簿格式要求", expanded=False):
    st.markdown(
        """
        一个 `.xlsx` 文件内需要包含 5 个工作表：`orders`、`stores`、`products`、`inventory`、`promotions`。

        - `orders`：订单明细，至少包含 order_id、date、store_id、product_id、city、category、quantity、gmv、refund_flag、is_promo。
        - `stores`：门店资料，至少包含 store_id、store_name、city、region、store_type。
        - `products`：商品资料，至少包含 product_id、product_name、brand、category、cost_price、sale_price。
        - `inventory`：库存明细，至少包含 date、store_id、product_id、stock_qty、safety_stock。
        - `promotions`：促销配置，至少包含 promotion_id、product_id、start_date、end_date、discount_rate。
        """
    )
    if SAMPLE_EXCEL.exists():
        st.download_button(
            "下载示例 Excel",
            SAMPLE_EXCEL.read_bytes(),
            file_name="sample_o2o_upload.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

uploaded = st.file_uploader("上传 Excel 数据源", type=["xlsx"])

try:
    if uploaded is None:
        st.info("当前使用内置示例数据。上传 Excel 后，页面会自动切换为你的文件数据。")
        data = load_sample_data()
    else:
        data = read_workbook(uploaded)
        st.success("Excel 数据读取成功。")
except Exception as exc:
    st.error(f"Excel 读取失败：{exc}")
    st.stop()

orders = data["orders"]
stores = data["stores"]
products = data["products"]
inventory = data["inventory"]
promotions = data["promotions"]
rules = load_rules()

with st.sidebar:
    st.header("筛选条件")
    min_date = orders["date"].min().date()
    max_date = orders["date"].max().date()
    selected_dates = st.date_input("日期范围", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    if len(selected_dates) != 2:
        st.stop()
    selected_cities = st.multiselect("城市", sorted(orders["city"].dropna().unique()), default=sorted(orders["city"].dropna().unique()))
    selected_categories = st.multiselect(
        "品类", sorted(orders["category"].dropna().unique()), default=sorted(orders["category"].dropna().unique())
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

if orders_f.empty:
    st.warning("当前筛选条件下没有订单数据，请调整日期、城市或品类。")
    st.stop()

daily = daily_metrics(orders_f, inventory_f)
store = store_metrics(orders_f, inventory_f, stores[stores["city"].isin(selected_cities)])
anomalies = detect_anomalies(orders_f, inventory_f, stores, rules)
product_view = product_inventory_view(orders_f, inventory_f, products)
promo = promo_view(orders_f, promotions, products)

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

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["经营看板", "异常门店", "商品库存", "促销复盘", "规则配置", "AI分析总结", "自助探索分析"])

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
    promo["promo_lift_text"] = promo["promo_lift"].map(pct_text)
    fig = px.bar(promo, x="product_name", y="promo_lift", color="category", title="促销前后 GMV 提升率")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(promo, use_container_width=True, hide_index=True)

with tab5:
    st.subheader("YAML 异常规则配置")
    st.code(RULES_PATH.read_text(encoding="utf-8"), language="yaml")
    st.info("面试讲法：新增客户指标或异常规则时，优先调整配置文件，减少重复改代码。")

with tab6:
    st.subheader("AI自动分析总结")
    st.caption("基于当前上传数据、筛选条件、核心指标、异常规则和促销结果自动生成经营分析结论。")
    summary = build_ai_summary(
        total_gmv,
        order_count,
        aov,
        refund_rate,
        stockout_rate,
        daily,
        store,
        anomalies,
        product_view,
        promo,
    )
    for item in summary:
        st.markdown(f"- {item}")
    st.download_button(
        "下载分析总结 TXT",
        "\n".join(summary),
        file_name="ai_analysis_summary.txt",
        mime="text/plain",
    )

with tab7:
    st.subheader("PyGWalker 自助探索分析")
    st.caption("上传 Excel 后，可把不同业务表交给用户自行拖拽字段做图，适合临时探索分析。")

    explore_orders = orders_f.merge(
        stores[["store_id", "store_name", "region", "store_type"]],
        on="store_id",
        how="left",
    ).merge(
        products[["product_id", "product_name", "brand"]],
        on="product_id",
        how="left",
    )
    explore_inventory = inventory_f.merge(
        stores[["store_id", "store_name", "city", "region", "store_type"]],
        on="store_id",
        how="left",
    ).merge(
        products[["product_id", "product_name", "brand", "category"]],
        on="product_id",
        how="left",
    )

    dataset_options = {
        "订单经营明细": explore_orders,
        "库存明细": explore_inventory,
        "商品库存汇总": product_view,
        "促销复盘结果": promo,
        "异常门店清单": anomalies,
    }
    selected_dataset = st.selectbox("选择要探索的数据表", list(dataset_options.keys()))
    render_pygwalker_explorer(dataset_options[selected_dataset])
