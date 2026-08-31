"""Streamlit dashboard: search Depop for the cheapest matching listing, and
track price drops on your Depop wishlist.
"""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

import alerts
import config
import db
import depop_client

st.set_page_config(page_title="Depop Price Tracker", page_icon="🧦", layout="wide")

db.init_db()

CONDITION_OPTIONS = [(None, "Any condition")] + list(depop_client.CONDITIONS)


def search_tab():
    st.subheader("Find the cheapest listing on Depop")
    with st.form("search_form"):
        query = st.text_input("What are you looking for?", placeholder="grey polo ralph lauren shirt")
        col1, col2 = st.columns(2)
        with col1:
            condition_label = st.selectbox(
                "Minimum condition",
                options=[label for _value, label in CONDITION_OPTIONS],
            )
        with col2:
            limit = st.slider("Results to show", min_value=5, max_value=30, value=10)
        submitted = st.form_submit_button("Search Depop")

    if submitted:
        if not query:
            st.error("Enter something to search for.")
        else:
            min_condition = dict((label, value) for value, label in CONDITION_OPTIONS)[condition_label]
            with st.spinner("Searching Depop (this drives a real headless browser, ~10-15s)..."):
                try:
                    st.session_state["depop_search_results"] = depop_client.search(
                        query, min_condition=min_condition, limit=limit
                    )
                except depop_client.DepopError as exc:
                    st.error(f"Search failed: {exc}")
                    st.session_state.pop("depop_search_results", None)

    # Read from session_state (not a local variable) so results -- and their
    # "Track this" buttons -- keep rendering across reruns triggered by
    # clicking one of those buttons, not just the rerun right after submit.
    results = st.session_state.get("depop_search_results")
    if results is None:
        return
    if not results:
        st.info("No results found. Try a broader search or a lower minimum condition.")
        return

    st.success(f"Cheapest match: **{results[0]['title']}** ({results[0]['size'] or 'no size listed'}) at **\\${results[0]['price']:.2f}**")

    for i, r in enumerate(results):
        cols = st.columns([3, 1, 1, 2])
        cols[0].markdown(f"[{r['title']} — {r['size'] or ''}]({r['url']})")
        if r["original_price"]:
            cols[1].markdown(f"~~\\${r['original_price']:.2f}~~ **\\${r['price']:.2f}**")
        else:
            cols[1].markdown(f"**\\${r['price']:.2f}**")
        cols[2].markdown("🥇 cheapest" if i == 0 else "")
        if cols[3].button("Track this", key=f"track-{i}-{r['url']}"):
            if db.product_exists(r["url"]):
                st.info("Already tracking this listing.")
            else:
                db.add_product(r["title"], r["url"], threshold=r["price"])
                st.success("Added to your tracked listings -- see the Wishlist tab.")


def wishlist_sync_section():
    username = config.get_depop_username()
    if not username:
        st.warning(
            "No Depop session set up. Run `python depop_login.py` in your terminal to log in "
            "once, then come back here to sync your wishlist."
        )
        return

    st.caption(f"Signed in as **{username}**")
    if st.button("Sync my Depop wishlist"):
        with st.spinner("Fetching your liked items from Depop..."):
            try:
                liked = depop_client.get_wishlist(Path(config.DEPOP_SESSION_PATH), username)
            except depop_client.NotLoggedInError as exc:
                st.error(f"{exc}")
                return

            added = 0
            for item in liked:
                if db.product_exists(item["url"]):
                    continue
                db.add_product(item["title"], item["url"], threshold=item["price"])
                added += 1
        st.success(f"Synced {len(liked)} liked items ({added} newly tracked).")
        st.rerun()


def add_manual_form():
    with st.expander("Track a specific listing by URL"):
        with st.form("add_manual", clear_on_submit=True):
            url = st.text_input("Depop listing URL", placeholder="https://www.depop.com/products/...")
            threshold = st.number_input("Alert me when price drops below", min_value=0.0, step=1.0)
            submitted = st.form_submit_button("Add & verify")

        if not submitted:
            return
        if not url:
            st.error("Enter a listing URL.")
            return

        with st.spinner("Checking listing..."):
            try:
                listing = depop_client.get_listing(url)
            except depop_client.DepopError as exc:
                st.error(f"Couldn't load that listing: {exc}")
                return

        if db.product_exists(url):
            st.info("Already tracking this listing.")
            return

        product_id = db.add_product(listing["title"], url, threshold)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.insert_price(product_id, listing["price"], timestamp)
        st.success(f"Added **{listing['title']}** at ${listing['price']:.2f}.")
        st.rerun()


def product_picker(products):
    labels = {p["id"]: f"{p['name']}  —  ${p['threshold']:.2f} threshold" for p in products}
    selected_id = st.selectbox(
        "Tracked listings", options=list(labels.keys()), format_func=lambda pid: labels[pid]
    )
    return db.get_product(selected_id)


def product_detail(product):
    history = db.get_history(product["id"])

    top = st.columns([2, 1, 1, 1])
    top[0].markdown(f"### {product['name']}")
    top[0].markdown(f"[View on Depop]({product['url']})")

    if history:
        latest = history[-1]["price"]
        top[1].metric("Latest price", f"${latest:.2f}")
        below = latest <= product["threshold"]
        top[2].metric("Threshold", f"${product['threshold']:.2f}", delta="below ✅" if below else "above")
    else:
        top[1].metric("Latest price", "—")
        top[2].metric("Threshold", f"${product['threshold']:.2f}")

    if top[3].button("Check now", key=f"check-{product['id']}"):
        with st.spinner("Checking Depop..."):
            try:
                listing = depop_client.get_listing(product["url"])
            except depop_client.DepopError as exc:
                st.error(f"Check failed: {exc}")
                return
            if not listing["available"]:
                st.warning("This listing is sold / no longer available.")
                return
            previous = db.get_latest_price(product["id"])
            previous_price = previous["price"] if previous else None
            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            db.insert_price(product["id"], listing["price"], timestamp)
            alerts.check_and_alert(product, listing["price"], previous_price)
        st.rerun()

    if not history:
        st.info("No price history yet — click **Check now** to fetch the first data point.")
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

    with st.expander("Remove this listing"):
        if st.button("Confirm remove", key=f"remove-{product['id']}"):
            db.remove_product(product["id"])
            st.rerun()


def wishlist_tab():
    wishlist_sync_section()
    add_manual_form()
    st.divider()

    products = db.list_products()
    if not products:
        st.info("Nothing tracked yet. Sync your wishlist or add a listing above.")
        return

    product = product_picker(products)
    st.divider()
    product_detail(product)


def main():
    st.title("🧦 Depop Price Tracker")
    st.caption("Find the cheapest listing on Depop, and get alerted when your wishlist drops in price.")

    tab1, tab2 = st.tabs(["🔍 Search Depop", "❤️ My Wishlist"])
    with tab1:
        search_tab()
    with tab2:
        wishlist_tab()


if __name__ == "__main__":
    main()
