import os
from typing import Dict, Any
import pandas as pd
import streamlit as st

HISTORY_PATH = "history.csv"

COLUMNS = [
    "slip_id", "created_at", "bankroll", "aggression", "demons_blocked", "sports_allowed",
    "stake_primary", "stake_secondary", "primary_slip_json",
    "result", "payout", "notes",
]

def load_history() -> pd.DataFrame:
    if os.path.exists(HISTORY_PATH):
        df = pd.read_csv(HISTORY_PATH)
        for c in COLUMNS:
            if c not in df.columns:
                df[c] = ""
        return df[COLUMNS]
    return pd.DataFrame(columns=COLUMNS)

def append_slip_to_history(row: Dict[str, Any]) -> None:
    df = load_history()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(HISTORY_PATH, index=False)

def update_slip_result(slip_id: str, result: str, payout: str, notes: str) -> None:
    df = load_history()
    if df.empty:
        return
    mask = df["slip_id"].astype(str) == str(slip_id)
    if not mask.any():
        st.error("Slip ID not found.")
        return
    df.loc[mask, "result"] = result
    df.loc[mask, "payout"] = payout
    df.loc[mask, "notes"] = notes
    df.to_csv(HISTORY_PATH, index=False)

def history_download_button():
    df = load_history()
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download History CSV (backup / move devices)",
        data=csv,
        file_name="prop_slip_history.csv",
        mime="text/csv",
    )
