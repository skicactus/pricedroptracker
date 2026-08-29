"""Streamlit dashboard: add products by URL, view price history charts."""

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

import alerts
import db
import scraper

st.set_page_config(page_title="Price Drop Tracker", page_icon="📉", layout="wide")

db.init_db()


def add_product_form():
    st.subheader("Track a new product")
    st.caption(
        "Paste a product page URL from any store. We'll try to auto-detect the price "
        "from the page's structured data before saving it."
    )
    with st.form("add_product", clear_on_submit=True):
        url = st.text_input("Product URL", placeholder="https://example.com/product/some-item")
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Name (optional, auto-filled from the page if blank)")
        with col2:
            threshold = st.number_input("Alert me when price drops below", min_value=0.0, step=1.0)
        with st.expander("Advanced: manual CSS selector (only needed if auto-detect fails)"):
            selector = st.text_input("CSS selector", placeholder=".price, span#priceblock, etc.")
        submitted = st.form_submit_button("Add & verify")

    if not submitted:
        return

    if not url:
        st.error("Enter a product URL.")
        return

    with st.spinner("Fetching page and detecting price..."):
        try:
            soup = scraper.fetch_page(url)
            price = scraper.extract_price(soup, selector or None)
        except scraper.FetchError as exc:
            st.error(f"Couldn't fetch that page: {exc}")
            return
        except scraper.PriceNotFoundError as exc:
            st.error(
                f"{exc}. This can happen when a site renders its price with JavaScript, "
                "or blocks automated requests. Try the manual CSS selector field above, "
                "or a different product URL."
            )
            return

        resolved_name = name.strip() or scraper.extract_title(soup) or url

    try:
        product_id = db.add_product(resolved_name, url, threshold, selector or None)
    except Exception as exc:  # e.g. UNIQUE constraint on url
        st.error(f"Couldn't save product: {exc}")
        return

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db.insert_price(product_id, price, timestamp)

    st.success(f"Added **{resolved_name}** at ${price:.2f}.")
    st.rerun()


def product_picker(products):
    labels = {p["id"]: f"{p['name']}  —  ${p['threshold']:.2f} threshold" for p in products}
    selected_id = st.selectbox(
        "Tracked products",
        options=list(labels.keys()),
        format_func=lambda pid: labels[pid],
    )
    return db.get_product(selected_id)


def product_detail(product):
    history = db.get_history(product["id"])

    top = st.columns([2, 1, 1, 1])
    top[0].markdown(f"### {product['name']}")
    top[0].markdown(f"[View product]({product['url']})")

    if history:
        latest = history[-1]["price"]
        top[1].metric("Latest price", f"${latest:.2f}")
        below = latest <= product["threshold"]
        top[2].metric("Threshold", f"${product['threshold']:.2f}", delta="below ✅" if below else "above")
    else:
        top[1].metric("Latest price", "—")
        top[2].metric("Threshold", f"${product['threshold']:.2f}")

    action_cols = top[3]
    if action_cols.button("Scrape now", key=f"scrape-{product['id']}"):
        with st.spinner("Scraping..."):
            try:
                price = scraper.scrape_price(product["url"], product["selector"])
            except (scraper.FetchError, scraper.PriceNotFoundError) as exc:
                st.error(f"Scrape failed: {exc}")
                return
            previous = db.get_latest_price(product["id"])
            previous_price = previous["price"] if previous else None
            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            db.insert_price(product["id"], price, timestamp)
            alerts.check_and_alert(product, price, previous_price)
        st.rerun()

    if not history:
        st.info("No price history yet — click **Scrape now** to fetch the first data point.")
    else:
        df = pd.DataFrame([dict(row) for row in history])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        chart_df = df.set_index("timestamp")[["price"]].rename(columns={"price": "Price ($)"})
        st.line_chart(chart_df)

        st.markdown("#### Price history")
        table_df = df[["timestamp", "price"]].rename(
            columns={"timestamp": "Timestamp", "price": "Price ($)"}
        ).sort_values("Timestamp", ascending=False)
        st.dataframe(table_df, use_container_width=True, hide_index=True)

    with st.expander("Remove this product"):
        st.warning("This deletes the product and all of its price history.")
        if st.button("Confirm remove", key=f"remove-{product['id']}"):
            db.remove_product(product["id"])
            st.rerun()


def main():
    st.title("📉 Price Drop Tracker")
    st.caption(
        "Track prices on any product page, get alerted when they drop below your threshold."
    )

    add_product_form()
    st.divider()

    products = db.list_products()
    if not products:
        st.info("No products tracked yet. Add one above to get started.")
        return

    product = product_picker(products)
    st.divider()
    product_detail(product)


if __name__ == "__main__":
    main()
