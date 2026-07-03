from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RNG = np.random.default_rng(42)
random.seed(42)


def make_stores() -> pd.DataFrame:
    cities = ["Shanghai", "Hangzhou", "Suzhou", "Nanjing", "Wuxi", "Ningbo"]
    regions = {
        "Shanghai": "East-1",
        "Hangzhou": "East-2",
        "Suzhou": "East-1",
        "Nanjing": "East-3",
        "Wuxi": "East-3",
        "Ningbo": "East-2",
    }
    store_types = ["Community", "Mall", "Campus", "Office", "Transport"]
    rows = []
    for i in range(1, 61):
        city = random.choice(cities)
        rows.append(
            {
                "store_id": f"S{i:03d}",
                "store_name": f"{city} Store {i:03d}",
                "city": city,
                "region": regions[city],
                "store_type": random.choice(store_types),
                "open_date": pd.Timestamp("2024-01-01")
                + pd.Timedelta(days=int(RNG.integers(0, 680))),
            }
        )
    return pd.DataFrame(rows)


def make_products() -> pd.DataFrame:
    categories = {
        "Coffee": ["Latte", "Americano", "Cold Brew", "Mocha"],
        "Snack": ["Protein Bar", "Chips", "Cookie", "Nuts"],
        "Dairy": ["Yogurt", "Milk", "Cheese Stick", "Milk Tea"],
        "Ready Meal": ["Salad", "Rice Bowl", "Sandwich", "Pasta"],
        "Beauty": ["Face Mask", "Hand Cream", "Cleanser", "Sunscreen"],
    }
    brands = ["FreshGo", "DailyPlus", "UrbanLife", "MPS Select", "O2O Mart"]
    rows = []
    idx = 1
    for category, names in categories.items():
        for name in names:
            price = float(RNG.integers(12, 89))
            rows.append(
                {
                    "product_id": f"P{idx:03d}",
                    "product_name": name,
                    "brand": random.choice(brands),
                    "category": category,
                    "cost_price": round(price * float(RNG.uniform(0.45, 0.68)), 2),
                    "sale_price": round(price, 2),
                }
            )
            idx += 1
    return pd.DataFrame(rows)


def make_promotions(products: pd.DataFrame) -> pd.DataFrame:
    promo_products = products.sample(10, random_state=7)["product_id"].tolist()
    rows = []
    starts = [pd.Timestamp("2026-05-06"), pd.Timestamp("2026-05-20"), pd.Timestamp("2026-06-03")]
    for i, product_id in enumerate(promo_products, start=1):
        start = starts[(i - 1) % len(starts)]
        rows.append(
            {
                "promotion_id": f"A{i:03d}",
                "product_id": product_id,
                "start_date": start,
                "end_date": start + pd.Timedelta(days=6),
                "discount_rate": round(float(RNG.uniform(0.72, 0.9)), 2),
            }
        )
    return pd.DataFrame(rows)


def make_inventory(stores: pd.DataFrame, products: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    product_ids = products["product_id"].tolist()
    for date in dates:
        for store_id in stores["store_id"]:
            stocked_products = random.sample(product_ids, 14)
            for product_id in stocked_products:
                base_stock = int(RNG.integers(8, 80))
                if date >= pd.Timestamp("2026-06-10") and store_id in ["S007", "S019", "S034"]:
                    base_stock = int(base_stock * RNG.uniform(0.1, 0.45))
                rows.append(
                    {
                        "date": date,
                        "store_id": store_id,
                        "product_id": product_id,
                        "stock_qty": base_stock,
                        "safety_stock": int(RNG.integers(10, 25)),
                    }
                )
    return pd.DataFrame(rows)


def make_orders(
    stores: pd.DataFrame,
    products: pd.DataFrame,
    promotions: pd.DataFrame,
    dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    promo_lookup = promotions.set_index("product_id").to_dict("index")
    product_map = products.set_index("product_id").to_dict("index")
    rows = []
    order_idx = 1
    for date in dates:
        weekday_factor = 1.25 if date.weekday() >= 5 else 1.0
        for store in stores.itertuples(index=False):
            city_factor = 1.25 if store.city in ["Shanghai", "Hangzhou"] else 0.95
            store_factor = float(RNG.uniform(0.75, 1.35))
            if date >= pd.Timestamp("2026-06-12") and store.store_id in ["S007", "S019", "S034"]:
                store_factor *= 0.55
            order_count = max(3, int(RNG.poisson(14 * weekday_factor * city_factor * store_factor)))
            for _ in range(order_count):
                product = products.sample(1, weights=products["sale_price"], random_state=int(RNG.integers(1, 999999))).iloc[0]
                product_id = product["product_id"]
                is_promo = False
                price = float(product["sale_price"])
                if product_id in promo_lookup:
                    promo = promo_lookup[product_id]
                    if promo["start_date"] <= date <= promo["end_date"]:
                        is_promo = True
                        price *= float(promo["discount_rate"])
                qty = int(RNG.choice([1, 1, 1, 2, 3]))
                status = "completed"
                refund_flag = 0
                if RNG.random() < 0.055:
                    status = "refunded"
                    refund_flag = 1
                rows.append(
                    {
                        "order_id": f"O{order_idx:07d}",
                        "date": date,
                        "store_id": store.store_id,
                        "product_id": product_id,
                        "city": store.city,
                        "category": product_map[product_id]["category"],
                        "quantity": qty,
                        "gmv": round(price * qty, 2),
                        "order_status": status,
                        "is_promo": int(is_promo),
                        "refund_flag": refund_flag,
                    }
                )
                order_idx += 1
    return pd.DataFrame(rows)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2026-05-01", "2026-06-30", freq="D")
    stores = make_stores()
    products = make_products()
    promotions = make_promotions(products)
    inventory = make_inventory(stores, products, dates)
    orders = make_orders(stores, products, promotions, dates)

    for name, df in {
        "stores": stores,
        "products": products,
        "promotions": promotions,
        "inventory": inventory,
        "orders": orders,
    }.items():
        df.to_csv(DATA_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")

    print(f"Generated {len(orders):,} orders, {len(inventory):,} inventory rows.")


if __name__ == "__main__":
    main()
