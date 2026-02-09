import os
import json
import uuid
from datetime import datetime

import pandas as pd
import streamlit as st

from slip_logic import (
    DEFAULT_MARKETS,
    normalize_last5,
    score_prop,
    build_recommendations_locked,
)
from tracking import (
    load_slips,
    load_props,
    save_slip,
    save_props,
    update_slip_result,
    update_prop_result,
    download_buttons,
)

st.set_page_config(page_title="PP Bankroll Builder (Manual)", layout="wide")

st.title("PP Bankroll Builder (Manual) — Aggression 1 (LOCKED)")
st.caption(
    "Manual entry (iPhone fast) • PrizePicks $5 min enforced • Bankroll gates locked • "
    "Primary: 3-pick flex when allowed • Demons blocked by default"
)

# -------------------------
# Session state
# -------------------------
if "board" not in st.session_state:
    st.session_state.board = []  # list[dict] each prop
if "today_slips_saved" not in st.session_state:
    st.session_state.today_slips_saved = 0

def now_iso():
    return datetime.utcnow().isoformat()

# -------------------------
# Sidebar
# -------------------------
st.sidebar.header("Daily Inputs")
bankroll = st.sidebar.number_input("Bankroll ($)", min_value=0.0, value=20.0, step=1.0)
aggression = st.sidebar.selectbox("Aggression", options=[1], index=0)
demons_blocked = st.sidebar.checkbox("Block Demons", value=True)

st.sidebar.divider()
st.sidebar.subheader("Maintenance")

if st.sidebar.button("🧹 RESET ALL TRACKING (Day 1 reset)"):
    # Delete local CSVs if they exist
    for f in ["slips_history.csv", "props_history.csv"]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass

    # Clear today's in-memory state too
    st.session_state.board = []
    st.session_state.today_slips_saved = 0
    st.sidebar.success("Tracking reset complete. Refreshing…")
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("LOCKED RULES (Aggression 1)")
st.sidebar.write("PrizePicks min bet: **$5**")
st.sidebar.write("Bankroll gates are **locked** — no overriding.")
st.sidebar.write("If board isn’t strong → **SKIP**.")

with st.expander("Bankroll gates (locked)", expanded=False):
    st.markdown(
        """
**$20–$49**
- Max slips/day: **1**
- Stake: **$5**
- Allowed: **2-pick FLEX** (default)  
- **3-pick FLEX only if board is ELITE**

**$50–$84**
- Max slips/day: **1**
- Stake: **$5**
- Allowed: **3-pick FLEX** (primary), or 2-pick if board weak

**$85–$149**
- Max slips/day: **2** (only if board strong)
- Stake: **$5 per slip** (max $10/day)
- Allowed: 3-pick FLEX, rare 4-pick FLEX if elite

**$150+**
- Max slips/day: **2**
- Stake: **$5 per slip** (max $10/day)
- Allowed: 3–5 pick FLEX if elite  
- **6-pick unlocked** only if board is INSANE (and counts as slip #2)
"""
    )

# -------------------------
# Step 1 — Add props manually (Option A)
# -------------------------
st.header("1) Add props (one at a time)")
st.write("Goal daily: **8–10 props** for best board selection.")

with st.form("add_prop_form", clear_on_submit=True):
    c1, c2, c3, c4 = st.columns([1.4, 1.6, 1.0, 1.0])

    sport = c1.selectbox("Sport", ["NBA", "SOCCER", "TENNIS", "NFL", "NHL", "MLB", "OTHER"], index=0)
    player = c2.text_input("Player (ex: Alperen Sengun)")
    market = c3.selectbox("Market", DEFAULT_MARKETS, index=0)
    line = c4.number_input("Line", value=0.0, step=0.5)

    c5, c6, c7 = st.columns([2.4, 1.0, 1.0])
    last5_str = c5.text_input("Last 5 values (paste like: 13 14 16 9 9)")
    is_goblin = c6.checkbox("Goblin", value=False)
    is_demon = c7.checkbox("Demon", value=False)

    submitted = st.form_submit_button("➕ Add Prop")

    if submitted:
        if not player.strip():
            st.error("Player is required.")
        elif line == 0.0:
            st.error("Line must be set (not 0).")
        else:
            last5 = normalize_last5(last5_str)
            prop = {
                "prop_id": str(uuid.uuid4())[:8],
                "sport": sport,
                "player": player.strip(),
                "market": market,
                "line": float(line),
                "last5": last5,  # list[float] length 5 or []
                "is_goblin": bool(is_goblin),
                "is_demon": bool(is_demon),
            }
            st.session_state.board.append(prop)
            st.success("Added!")

# Board view + quick actions
st.subheader("Current board")
if not st.session_state.board:
    st.info("Add a few props to get started.")
else:
    df_board = pd.DataFrame(st.session_state.board)
    st.dataframe(df_board, use_container_width=True, height=260)

colA, colB, colC = st.columns([1, 1, 2])
with colA:
    if st.button("🧹 Clear board"):
        st.session_state.board = []
        st.session_state.today_slips_saved = 0
        st.rerun()

with colB:
    # NOTE: download button must be called unconditionally, so we create it here safely
    payload = {
        "saved_at": now_iso(),
        "bankroll": bankroll,
        "board": st.session_state.board,
    }
    st.download_button(
        "⬇️ Download board JSON",
        data=json.dumps(payload, indent=2).encode("utf-8"),
        file_name="pp_board_backup.json",
        mime="application/json",
        disabled=(len(st.session_state.board) == 0),
    )

# -------------------------
# Step 2 — Score board
# -------------------------
st.header("2) Score board + Build slips")

if st.session_state.board:
    scored = []
    for p in st.session_state.board:
        scored.append(score_prop(p, demons_blocked=demons_blocked))

    df_scored = pd.DataFrame(scored).sort_values("score", ascending=False)
    st.subheader("Ranked props (top = best)")
    st.dataframe(df_scored, use_container_width=True, height=340)

    # -------------------------
    # Step 3 — Recommendations (locked)
    # -------------------------
    st.header("3) Recommendation (PLAY vs SKIP) — Locked rules")

    rec = build_recommendations_locked(
        scored_props=scored,
        bankroll=float(bankroll),
        demons_blocked=bool(demons_blocked),
        slips_already_saved=int(st.session_state.today_slips_saved),
    )

    if rec["action"] == "SKIP":
        st.error(f"SKIP: {rec['reason']}")
    else:
        st.success(f"PLAY: {rec['summary']}")
        st.write(rec["reason"])

        for idx, slip in enumerate(rec["slips"], start=1):
            st.markdown(f"### Slip {idx}: {slip['slip_type']} — Stake **${slip['stake']:.2f}**")
            st.dataframe(pd.DataFrame(slip["legs"]), use_container_width=True, height=220)

        if st.button("✅ Save recommended slip(s) to tracking", type="primary"):
            created_at = now_iso()

            for slip in rec["slips"]:
                slip_id = str(uuid.uuid4())[:8]
                save_slip({
                    "slip_id": slip_id,
                    "created_at": created_at,
                    "bankroll": float(bankroll),
                    "aggression": 1,
                    "stake": float(slip["stake"]),
                    "slip_type": slip["slip_type"],
                    "action": "PLAY",
                    "reason": rec["reason"],
                    "result": "",
                    "payout": "",
                    "notes": "",
                    "legs_json": json.dumps(slip["legs"]),
                })

                prop_rows = []
                for i, leg in enumerate(slip["legs"], start=1):
                    prop_rows.append({
                        "slip_id": slip_id,
                        "prop_id": f"{slip_id}-{i}",
                        "created_at": created_at,
                        "player": leg.get("player",""),
                        "market": leg.get("market",""),
                        "side": leg.get("pick",""),
                        "line": leg.get("line",""),
                        "score": leg.get("score",""),
                        "result": "",
                    })
                save_props(prop_rows)

            st.session_state.today_slips_saved += len(rec["slips"])
            st.success("Saved to tracking. Scroll down to update results after games.")

# -------------------------
# Step 4 — Tracking
# -------------------------
st.header("4) Track results (Prop + Slip)")

slips_df = load_slips()
props_df = load_props()

if slips_df.empty:
    st.info("No saved slips yet. Save a slip above to start tracking.")
else:
    st.subheader("Slip history")
    st.dataframe(slips_df.sort_values("created_at", ascending=False), use_container_width=True)

    st.subheader("Update slip result")
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    with c1:
        slip_id_in = st.text_input("Slip ID")
    with c2:
        slip_result = st.selectbox("Slip Result", ["", "W", "L", "PARTIAL"])
    with c3:
        payout = st.text_input("Payout ($)")
    with c4:
        notes = st.text_input("Notes")

    if st.button("Update Slip"):
        if not slip_id_in.strip():
            st.error("Enter a Slip ID.")
        else:
            update_slip_result(slip_id_in.strip(), slip_result, payout, notes)
            st.success("Slip updated (refresh if needed).")

    st.subheader("Prop legs + update prop results")
    st.dataframe(props_df.sort_values("created_at", ascending=False), use_container_width=True)

    c5, c6, c7 = st.columns([1, 1, 1])
    with c5:
        slip_id_leg = st.text_input("Slip ID (for leg)")
    with c6:
        prop_id_leg = st.text_input("Prop ID (example: ab12cd34-1)")
    with c7:
        prop_res = st.selectbox("Prop Result", ["", "WIN", "LOSS", "PUSH", "DNP"])

    if st.button("Update Prop"):
        if not slip_id_leg.strip() or not prop_id_leg.strip():
            st.error("Enter Slip ID and Prop ID.")
        else:
            update_prop_result(slip_id_leg.strip(), prop_id_leg.strip(), prop_res)
            st.success("Prop updated (refresh if needed).")

    st.subheader("Backups")
    download_buttons()