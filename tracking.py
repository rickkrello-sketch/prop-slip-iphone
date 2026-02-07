import os
import pandas as pd
import streamlit as st

SLIPS_PATH = "slips_history.csv"
PROPS_PATH = "props_history.csv"

SLIP_COLS = [
    "slip_id","created_at","bankroll","aggression","stake","slip_type",
    "action","reason","result","payout","notes","legs_json"
]

PROP_COLS = [
    "slip_id","prop_id","created_at","player","market","side","line","score","result"
]

def _load_csv(path: str, cols: list) -> pd.DataFrame:
    if os.path.exists(path):
        df = pd.read_csv(path)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols]
    return pd.DataFrame(columns=cols)

def load_slips() -> pd.DataFrame:
    return _load_csv(SLIPS_PATH, SLIP_COLS)

def load_props() -> pd.DataFrame:
    return _load_csv(PROPS_PATH, PROP_COLS)

def save_slip(row: dict):
    df = load_slips()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(SLIPS_PATH, index=False)

def save_props(rows: list):
    df = load_props()
    df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    df.to_csv(PROPS_PATH, index=False)

def update_slip_result(slip_id: str, result: str, payout: str, notes: str):
    df = load_slips()
    mask = df["slip_id"].astype(str) == str(slip_id)
    if not mask.any():
        st.error("Slip ID not found.")
        return
    df.loc[mask, "result"] = result
    df.loc[mask, "payout"] = payout
    df.loc[mask, "notes"] = notes
    df.to_csv(SLIPS_PATH, index=False)

def update_prop_result(slip_id: str, prop_id: str, result: str):
    df = load_props()
    mask = (df["slip_id"].astype(str) == str(slip_id)) & (df["prop_id"].astype(str) == str(prop_id))
    if not mask.any():
        st.error("Prop ID not found for that slip.")
        return
    df.loc[mask, "result"] = result
    df.to_csv(PROPS_PATH, index=False)

def download_buttons():
    slips = load_slips().to_csv(index=False).encode("utf-8")
    props = load_props().to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download slips history CSV", slips, "slips_history.csv", "text/csv")
    st.download_button("⬇️ Download props history CSV", props, "props_history.csv", "text/csv")