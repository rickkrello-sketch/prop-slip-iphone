import os
import json
import uuid
import base64
from datetime import datetime
from typing import List, Dict, Any, Optional

import pandas as pd
import streamlit as st

from vision_extract import extract_props_from_images
from slip_logic import (
    filter_props,
    score_props_simple,
    build_primary_slip_aggression_1,
    recommend_stake_aggression_1,
)
from tracking import (
    load_history,
    append_slip_to_history,
    update_slip_result,
    history_download_button,
)

APP_TITLE = "Prop + Slip (iPhone) — Bankroll Builder"

st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)
st.caption("Upload PrizePicks prop screenshots → extract props → pick More/Less → build slips → track results.")

# --- Sidebar controls ---
st.sidebar.header("Daily Inputs")

bankroll = st.sidebar.number_input("Current Bankroll ($)", min_value=0.0, value=20.0, step=1.0)
aggression = st.sidebar.selectbox("Aggression Level", options=[1, 2, 3], index=0)
sports_allowed = st.sidebar.multiselect(
    "Sports allowed today",
    options=["NBA", "WNBA", "NFL", "MLB", "NHL", "SOCCER", "TENNIS", "CBB", "OTHER"],
    default=["NBA"],
)

demons_blocked = st.sidebar.checkbox("Block Demons (recommended)", value=True)
max_screenshots = st.sidebar.slider("Max screenshots to upload", min_value=1, max_value=20, value=10)

st.sidebar.divider()
st.sidebar.subheader("Tracking")
st.sidebar.write("You can log results after games. The app will learn from your history.")

# --- Upload screenshots ---
st.header("1) Upload prop screenshots")
uploads = st.file_uploader(
    "Upload 1–10 screenshots (PNG/JPG).",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
)

if uploads and len(uploads) > max_screenshots:
    st.warning(f"You uploaded {len(uploads)} files. Only first {max_screenshots} will be used.")
    uploads = uploads[:max_screenshots]

# --- Extract ---
extracted: List[Dict[str, Any]] = []
if uploads:
    if not os.getenv("OPENAI_API_KEY") and not st.secrets.get("OPENAI_API_KEY", None):
        st.error("Missing OPENAI_API_KEY. Add it in Streamlit secrets.")
        st.stop()

    with st.spinner("Reading screenshots (vision) and extracting props…"):
        extracted = extract_props_from_images(uploads)

    st.success(f"Extracted {len(extracted)} prop(s) from screenshots.")

# --- Review extracted props ---
st.header("2) Review extracted props (edit if needed)")
if extracted:
    df = pd.DataFrame(extracted)
    # Friendly order
    cols = [c for c in ["sport", "player", "team", "opponent", "market", "line", "alt_line", "is_demon", "is_goblin", "game_time"] if c in df.columns]
    df = df[cols + [c for c in df.columns if c not in cols]]

    edited_df = st.data_editor(
        df,
        use_container_width=True,
        num_rows="dynamic",
        key="props_editor",
    )
    props = edited_df.to_dict(orient="records")
else:
    props = []

# --- Filter and score ---
st.header("3) Build slips")
if props:
    props = filter_props(
        props,
        sports_allowed=sports_allowed,
        demons_blocked=demons_blocked,
    )
    scored = score_props_simple(props)

    st.subheader("Top props (ranked)")
    scored_df = pd.DataFrame(scored).sort_values(by="score", ascending=False)
    st.dataframe(scored_df, use_container_width=True, height=320)

    if aggression != 1:
        st.info("Aggression 2/3 logic can be added next. Right now slips are tuned for Aggression=1 (safer).")

    primary_slip = build_primary_slip_aggression_1(scored)
    stake_primary, stake_secondary = recommend_stake_aggression_1(bankroll)

    st.subheader("Primary Slip (Aggression=1)")
    st.write("Default: **3-pick Flex** (demons blocked unless you toggle them on).")
    st.json(primary_slip)

    st.subheader("Stake recommendation")
    st.write(f"Primary slip stake: **${stake_primary:.2f}**")
    st.write(f"Optional secondary slip stake: **${stake_secondary:.2f}** (only if you want a 2nd card)")

    # Save slip to history
    if st.button("✅ Save today’s slip to History", type="primary"):
        slip_id = str(uuid.uuid4())[:8]
        payload = {
            "slip_id": slip_id,
            "created_at": datetime.utcnow().isoformat(),
            "bankroll": bankroll,
            "aggression": aggression,
            "demons_blocked": demons_blocked,
            "sports_allowed": ",".join(sports_allowed),
            "stake_primary": float(stake_primary),
            "stake_secondary": float(stake_secondary),
            "primary_slip_json": json.dumps(primary_slip),
            "result": "",  # W / L / PARTIAL later
            "payout": "",
            "notes": "",
        }
        append_slip_to_history(payload)
        st.success(f"Saved to History. Slip ID: {slip_id}")

# --- History / tracking ---
st.header("4) Track results")
hist = load_history()

if hist.empty:
    st.info("No history yet. Save a slip above to start tracking.")
else:
    st.dataframe(hist.sort_values("created_at", ascending=False), use_container_width=True)

    st.subheader("Update a slip result")
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])

    with col1:
        slip_id = st.text_input("Slip ID", value="")
    with col2:
        result = st.selectbox("Result", options=["", "W", "L", "PARTIAL"], index=0)
    with col3:
        payout = st.text_input("Payout ($)", value="")
    with col4:
        notes = st.text_input("Notes", value="")

    if st.button("Update Result"):
        if not slip_id:
            st.error("Enter a Slip ID.")
        else:
            update_slip_result(slip_id=slip_id.strip(), result=result, payout=payout, notes=notes)
            st.success("Updated. Refresh the page to see changes.")

    history_download_button()
