import os, json, uuid
from datetime import datetime
import pandas as pd
import streamlit as st

from vision_extract import extract_props_from_images
from slip_logic import filter_props, score_props, build_recommendation_aggression1
from tracking import (
    load_slips, load_props, save_slip, save_props,
    update_slip_result, update_prop_result, download_buttons
)

st.set_page_config(page_title="PP Bankroll Builder (iPhone)", layout="wide")
st.title("PP Bankroll Builder (iPhone) — Aggression 1 (Bankroll Mode)")
st.caption("PrizePicks $5 minimum enforced • $20 bankroll = one $5 slip/day • 2-pick flex only until $85+")

# Sidebar
st.sidebar.header("Daily Inputs")
bankroll = st.sidebar.number_input("Bankroll ($)", min_value=0.0, value=20.0, step=1.0)
sports_allowed = st.sidebar.multiselect(
    "Sports allowed today",
    ["NBA","WNBA","NFL","MLB","NHL","SOCCER","TENNIS","CBB","OTHER"],
    default=["NBA"]
)
demons_blocked = st.sidebar.checkbox("Block Demons", value=True)

st.sidebar.divider()
st.sidebar.subheader("PrizePicks rule")
st.sidebar.write("Minimum bet is $5. With $20 bankroll, app will recommend at most one $5 slip/day.")

# Uploads
st.header("1) Upload 1–10 prop screenshots")
uploads = st.file_uploader("Upload screenshots", type=["png","jpg","jpeg","webp"], accept_multiple_files=True)

if uploads and len(uploads) > 10:
    st.warning("Max 10 uploads at a time. Using first 10.")
    uploads = uploads[:10]

# Extract
props = []
if uploads:
    if not os.getenv("OPENAI_API_KEY") and not st.secrets.get("OPENAI_API_KEY", None):
        st.error("Missing OPENAI_API_KEY. Add it in Streamlit Cloud → Settings → Secrets.")
        st.stop()

    with st.spinner("Extracting props from screenshots…"):
        props = extract_props_from_images(uploads)

st.header("2) Review extracted props (edit if needed)")
if props:
    df = pd.DataFrame(props)
    edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    props = edited_df.to_dict(orient="records")
else:
    st.info("Upload screenshots to start.")
    st.stop()

# Build
st.header("3) Recommendation (PLAY vs SKIP)")
filtered = filter_props(props, sports_allowed=sports_allowed, demons_blocked=demons_blocked)
scored = score_props(filtered)

st.subheader("Ranked board")
st.dataframe(pd.DataFrame(scored).sort_values("score", ascending=False), use_container_width=True, height=360)

rec = build_recommendation_aggression1(scored, bankroll=float(bankroll))

if rec["action"] == "SKIP":
    st.error(f"SKIP: {rec['reason']}")
else:
    st.success(f"PLAY: {rec['slip_type']} • Stake: ${rec['stake']:.2f}")
    st.write(rec["reason"])
    st.json(rec)

    if st.button("✅ Save slip + legs to tracking", type="primary"):
        slip_id = str(uuid.uuid4())[:8]
        created_at = datetime.utcnow().isoformat()

        # Save slip
        save_slip({
            "slip_id": slip_id,
            "created_at": created_at,
            "bankroll": bankroll,
            "aggression": 1,
            "stake": rec["stake"],
            "slip_type": rec["slip_type"],
            "action": rec["action"],
            "reason": rec.get("reason",""),
            "result": "",
            "payout": "",
            "notes": "",
            "legs_json": json.dumps(rec["legs"]),
        })

        # Save legs as prop rows
        leg_rows = []
        for i, leg in enumerate(rec["legs"], start=1):
            prop_id = f"{slip_id}-{i}"
            leg_rows.append({
                "slip_id": slip_id,
                "prop_id": prop_id,
                "created_at": created_at,
                "player": leg.get("player",""),
                "market": leg.get("market",""),
                "side": leg.get("recommended",""),
                "line": leg.get("line",""),
                "score": leg.get("score",""),
                "result": "",  # set later
            })
        save_props(leg_rows)

        st.success(f"Saved! Slip ID: {slip_id}")

st.header("4) Track results (Prop + Slip)")
slips_df = load_slips()
props_df = load_props()

if slips_df.empty:
    st.info("No saved slips yet.")
else:
    st.subheader("Slip history")
    st.dataframe(slips_df.sort_values("created_at", ascending=False), use_container_width=True)

    st.subheader("Update slip result")
    c1, c2, c3, c4 = st.columns([1,1,1,2])
    with c1:
        slip_id_in = st.text_input("Slip ID")
    with c2:
        slip_result = st.selectbox("Slip Result", ["", "W", "L", "PARTIAL"])
    with c3:
        payout = st.text_input("Payout ($)")
    with c4:
        notes = st.text_input("Notes")

    if st.button("Update Slip"):
        update_slip_result(slip_id_in.strip(), slip_result, payout, notes)
        st.success("Slip updated (refresh if needed).")

    st.subheader("Prop legs (per slip) + update prop results")
    st.dataframe(props_df.sort_values("created_at", ascending=False), use_container_width=True)

    c5, c6, c7 = st.columns([1,1,1])
    with c5:
        slip_id_leg = st.text_input("Slip ID (for leg)")
    with c6:
        prop_id_leg = st.text_input("Prop ID (example: ab12cd34-1)")
    with c7:
        prop_res = st.selectbox("Prop Result", ["", "WIN", "LOSS", "PUSH", "DNP"])

    if st.button("Update Prop"):
        update_prop_result(slip_id_leg.strip(), prop_id_leg.strip(), prop_res)
        st.success("Prop updated (refresh if needed).")

    st.subheader("Backups")
    download_buttons()