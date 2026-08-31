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

st.set_page_config(page_title="Depop Price Tracker", page_icon="🧦", layout="centered")

db.init_db()

CONDITION_OPTIONS = [(None, "Any condition")] + list(depop_client.CONDITIONS)


def inject_custom_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600&display=swap');

        html, body, [class*="css"], .stApp {
            font-family: 'Inter', -apple-system, sans-serif;
        }

        h1, h2, h3, h4, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
            font-family: 'Fraunces', Georgia, serif;
            font-weight: 600;
            letter-spacing: -0.01em;
            color: #2A2118;
        }

        .block-container {
            padding-top: 3rem;
            padding-bottom: 5rem;
            max-width: 760px;
        }

        [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] {
            gap: 0.9rem;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 18px !important;
            border: 1px solid rgba(42, 33, 24, 0.10) !important;
            box-shadow: 0 1px 2px rgba(42, 33, 24, 0.04), 0 6px 20px rgba(42, 33, 24, 0.05);
            background: #FFFDFA;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            padding: 0.4rem 0.2rem;
        }

        button[kind="primary"], button[kind="secondary"] {
            border-radius: 10px !important;
            font-weight: 500 !important;
        }

        [data-testid="stMetricValue"] {
            font-family: 'Fraunces', Georgia, serif;
        }

        [data-testid="stTabs"] button [data-testid="stMarkdownContainer"] p {
            font-size: 1.02rem;
            font-weight: 500;
        }

        .cozy-caption {
            color: #7A6C5D;
            font-size: 0.92rem;
        }

        .cheapest-badge {
            display: inline-block;
            background: #E9DCC7;
            color: #7A4A1F;
            border-radius: 999px;
            padding: 0.1rem 0.7rem;
            font-size: 0.78rem;
            font-weight: 600;
            letter-spacing: 0.02em;
        }

        hr {
            margin: 2rem 0;
            border-color: rgba(42, 33, 24, 0.08);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def listing_row(r, key_prefix, on_track=True):
    with st.container(border=True):
        cols = st.columns([4, 2])
        with cols[0]:
            st.markdown(f"**[{r['title']}]({r['url']})**")
            meta_bits = [b for b in [r.get("size"), r.get("brand")] if b]
            if meta_bits:
                st.markdown(f'<span class="cozy-caption">{" · ".join(meta_bits)}</span>', unsafe_allow_html=True)
        with cols[1]:
            if r.get("original_price"):
                st.markdown(
                    f'<span class="cozy-caption">~~\\${r["original_price"]:.2f}~~</span> '
                    f'**\\${r["price"]:.2f}**',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f'**\\${r["price"]:.2f}**')
            if on_track:
                if st.button("Track this", key=f"{key_prefix}-{r['url']}"):
                    if db.product_exists(r["url"]):
                        st.info("Already tracking this listing.")
                    else:
                        db.add_product(r["title"], r["url"], threshold=r["price"])
                        st.success("Added -- see the Wishlist tab.")


def search_tab():
    st.subheader("Find the cheapest listing")
    st.markdown(
        '<p class="cozy-caption">Search all of Depop, sorted cheapest first, filtered by condition.</p>',
        unsafe_allow_html=True,
    )

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
        submitted = st.form_submit_button("Search Depop", type="primary")

    if submitted:
        if not query:
            st.error("Enter something to search for.")
        else:
            min_condition = dict((label, value) for value, label in CONDITION_OPTIONS)[condition_label]
            with st.spinner("Searching Depop (drives a real headless browser, can take up to ~30-40s)..."):
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

    st.markdown("")
    st.markdown(
        f'<span class="cheapest-badge">🥇 cheapest match</span>  &nbsp; '
        f'**{results[0]["title"]}** at **\\${results[0]["price"]:.2f}**',
        unsafe_allow_html=True,
    )
    st.markdown("")

    for i, r in enumerate(results):
        listing_row(r, key_prefix=f"track-{i}")


def wishlist_sync_section():
    username = config.get_depop_username()
    if not username:
        st.warning(
            "No Depop session set up. Run `python depop_login.py` in your terminal to log in "
            "once, then come back here to sync your wishlist."
        )
        return

    st.markdown(f'<p class="cozy-caption">Signed in as <b>{username}</b></p>', unsafe_allow_html=True)
    if st.button("Sync my Depop wishlist", type="primary"):
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


def cheaper_alternatives_section(product):
    st.markdown("#### Cheaper alternatives")
    st.markdown(
        '<p class="cozy-caption">Depop has no exact-match SKUs, so this searches by title -- '
        'results are similar listings from other sellers, not guaranteed identical items.</p>',
        unsafe_allow_html=True,
    )

    state_key = f"alts-{product['id']}"
    if st.button("Find cheaper alternatives", key=f"find-alts-{product['id']}"):
        history = db.get_history(product["id"])
        current_price = history[-1]["price"] if history else product["threshold"]
        with st.spinner("Searching Depop for similar listings..."):
            try:
                st.session_state[state_key] = depop_client.find_cheaper_alternatives(
                    product["name"], current_price=current_price, exclude_url=product["url"]
                )
            except depop_client.DepopError as exc:
                st.error(f"Search failed: {exc}")
                st.session_state.pop(state_key, None)

    alternatives = st.session_state.get(state_key)
    if alternatives is None:
        return
    if not alternatives:
        st.info("No cheaper alternatives found right now.")
        return

    for i, alt in enumerate(alternatives):
        listing_row(alt, key_prefix=f"{state_key}-track-{i}")


def product_detail(product):
    history = db.get_history(product["id"])

    with st.container(border=True):
        top = st.columns([2, 1, 1, 1])
        top[0].markdown(f"#### {product['name']}")
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

            st.markdown("###### Price history")
            table_df = df[["timestamp", "price"]].rename(
                columns={"timestamp": "Timestamp", "price": "Price ($)"}
            ).sort_values("Timestamp", ascending=False)
            st.dataframe(table_df, use_container_width=True, hide_index=True)

    st.markdown("")
    cheaper_alternatives_section(product)

    st.markdown("")
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
    st.markdown("")
    product_detail(product)


def main():
    inject_custom_css()

    st.title("🧦 Depop Price Tracker")
    st.markdown(
        '<p class="cozy-caption">Find the cheapest listing on Depop, and get alerted when your '
        "wishlist drops in price.</p>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    tab1, tab2 = st.tabs(["🔍 Search Depop", "❤️ My Wishlist"])
    with tab1:
        search_tab()
    with tab2:
        wishlist_tab()


if __name__ == "__main__":
    main()
