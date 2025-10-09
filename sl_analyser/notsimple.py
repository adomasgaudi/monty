# streamlit_app.py
import json
import re
import requests
import pandas as pd
import numpy as np
import streamlit as st

# ---------------------------------------
# Imports and constants (logic-only)
# ---------------------------------------
try:
    # Project-style import
    from SL_analyser.variables import NAME_TO_USERNAME, BW_PCT_RAW  # type: ignore
except Exception:
    try:
        # Flat-folder import
        from variables import NAME_TO_USERNAME, BW_PCT_RAW  # type: ignore
    except Exception:
        NAME_TO_USERNAME, BW_PCT_RAW = {}, {}

USER_AGENT = "Mozilla/5.0"
WORKOUTS_PAGE_TEMPLATE = "https://my.strengthlevel.com/{username}/workouts"
WORKOUTS_API_URL = "https://my.strengthlevel.com/api/workouts"
PREFILL_REGEX = re.compile(r"window\.prefill\s*=\s*(\[[\s\S]*?\]);")

# ---------- Data fetch (pure functions) ----------

def fetch_page(url: str) -> str:
    r = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    return r.text

def parse_prefill_for_user_id(html_text: str) -> str:
    m = PREFILL_REGEX.search(html_text)
    if not m:
        raise ValueError("prefill JSON not found in page")
    try:
        prefill = json.loads(m.group(1))
    except Exception as exc:
        raise ValueError("failed to parse prefill JSON") from exc

    for blob in prefill:
        req = blob.get("request", {})
        if req.get("url") == "/api/workouts":
            user_id = req.get("params", {}).get("user_id")
            if user_id:
                return user_id
    raise ValueError("user_id not found in prefill JSON")

def fetch_workouts_payload(user_id: str) -> dict:
    # NOTE: include bodyweight + rir/rpe so we can do the later transforms
    params = {
        "user_id": user_id,
        "workout.fields": "date,bodyweight,exercises",
        "workoutexercise.fields": "exercise_name,sets",
        "set.fields": "weight,reps,notes,rir,rpe",
        "limit": 1000,
        "offset": 0,
    }
    r = requests.get(WORKOUTS_API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.json()

def flatten_workouts(payload: dict) -> list[dict]:
    """
    Return a list of dict rows:
    date, bodyweight, exercise, weight, reps, rir, rpe, notes
    """
    rows: list[dict] = []
    for w in payload.get("data", []):
        date = w.get("date")
        bodyweight = w.get("bodyweight")
        for ex in (w.get("exercises") or []):
            ex_name = ex.get("exercise_name", "")
            for s in (ex.get("sets") or []):
                rows.append({
                    "date": date,
                    "bodyweight": bodyweight,
                    "exercise": ex_name,
                    "weight": s.get("weight"),
                    "reps": s.get("reps"),
                    "rir": s.get("rir"),
                    "rpe": s.get("rpe"),
                    "notes": s.get("notes"),
                })
    return rows

def safe_fetch_rows(username: str) -> tuple[list[dict], str | None]:
    try:
        html = fetch_page(WORKOUTS_PAGE_TEMPLATE.format(username=username))
        user_id = parse_prefill_for_user_id(html)
        payload = fetch_workouts_payload(user_id)
        rows = flatten_workouts(payload)
        return rows, None
    except requests.RequestException as exc:
        return [], f"Network error: {exc}"
    except ValueError as exc:
        return [], str(exc)
    except Exception as exc:
        return [], f"Unexpected error: {exc}"

# ---------- Transform helpers (pure functions) ----------

_BW_KEYMAP = {k.strip().lower(): v for k, v in BW_PCT_RAW.items()}

def _norm(s: str) -> str:
    return (s or "").strip().lower()

def to_dataframe(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    # normalize numeric columns
    for c in ["weight", "reps", "rir", "rpe", "bodyweight"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def add_bw_pct_and_internal_weight(df: pd.DataFrame) -> pd.DataFrame:
    """Add bw_pct (exercise → % bodyweight) and internal_weight = bodyweight * bw_pct."""
    df = df.copy()
    df["bw_pct"] = df["exercise"].map(lambda x: _BW_KEYMAP.get(_norm(x)))
    df["internal_weight"] = df["bodyweight"] * df["bw_pct"]
    return df

def epley3_1rm(reps: float | None, wi: float | None, x: float | None) -> float | np.nan:
    """
    Epley3 inversion you defined:
    R_epley3(x) = 100*(w_REC + w_i) / [3.33*(x + w_i)] - 29
    => w_REC = ((R + 29) * 3.33 * (x + w_i)) / 100 - w_i
    """
    if pd.isna(reps) or reps <= 0:
        return np.nan
    if pd.isna(wi):
        return np.nan
    if pd.isna(x):
        x = 0.0
    try:
        r = float(reps); wi = float(wi); x = float(x)
        return ((r + 29.0) * 3.33 * (x + wi)) / 100.0 - wi
    except Exception:
        return np.nan

def add_estimated_1rm(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["est_1RM"] = df.apply(lambda row: epley3_1rm(row.get("reps"), row.get("internal_weight"), row.get("weight")), axis=1)
    df["est_1RM"] = df["est_1RM"].round(1)
    return df

def table_bw_and_1rm(df: pd.DataFrame) -> pd.DataFrame:
    """
    Table #1: add bw% and 1RM; keep the most relevant columns for viewing.
    """
    df1 = add_bw_pct_and_internal_weight(df)
    df1 = add_estimated_1rm(df1)
    cols = ["date", "exercise", "weight", "reps", "rir", "rpe", "bodyweight", "bw_pct", "internal_weight", "est_1RM", "notes"]
    return df1[[c for c in cols if c in df1.columns]]

def table_single_exercise(df: pd.DataFrame, exercise_name: str) -> pd.DataFrame:
    """
    Table #2: filter to one exercise (case-insensitive), keep a tidy view.
    """
    m = df["exercise"].str.lower() == exercise_name.strip().lower()
    out = df.loc[m].copy()
    # If needed, add bw% + est_1RM too:
    out = add_bw_pct_and_internal_weight(out)
    out = add_estimated_1rm(out)
    keep = ["date", "exercise", "weight", "reps", "rir", "rpe", "est_1RM", "notes"]
    return out[[c for c in keep if c in out.columns]]

def summarize_hard_sets(df: pd.DataFrame, rir_min: int = 1, rir_max: int = 3) -> pd.DataFrame:
    """
    Table #3: count 'hard sets' (RIR in [1..3]) and show some simple aggregates.
    - Returns per-date, per-exercise counts + average 1RM of those hard sets.
    """
    work = add_bw_pct_and_internal_weight(df)
    work = add_estimated_1rm(work)

    # Hard sets: 1 <= RIR <= 3 (and RIR not null)
    mask = work["rir"].between(rir_min, rir_max, inclusive="both")
    hard = work.loc[mask].copy()

    if hard.empty:
        return pd.DataFrame(columns=["date", "exercise", "hard_sets", "avg_1RM"])

    grouped = (
        hard.groupby(["date", "exercise"], as_index=False)
            .agg(hard_sets=("rir", "count"), avg_1RM=("est_1RM", "mean"))
    )
    grouped["avg_1RM"] = grouped["avg_1RM"].round(1)
    return grouped.sort_values(["date", "exercise"])

# ---------- UI (thin) ----------

def get_names_for_ui() -> list[str]:
    names = list(NAME_TO_USERNAME.keys())
    return names if names else ["— no names —"]

def resolve_username(selected_name: str | None) -> str | None:
    if not selected_name or selected_name == "— no names —":
        return None
    return NAME_TO_USERNAME.get(selected_name)

# ---------------------------------------
# Streamlit
# ---------------------------------------
st.set_page_config(page_title="StrengthLevel DATA (data-first)")
st.title("StrengthLevel DATA (data-first)")

names = get_names_for_ui()
selected_name = st.selectbox("Select person", names, index=names.index("dzuljeta") if "dzuljeta" in names else 0)

username = resolve_username(selected_name)
if not username:
    st.error("No names available. Check variables module import.")
    st.stop()

rows, err = safe_fetch_rows(username)
if err:
    st.error(err)
    st.stop()

if not rows:
    st.info("No workouts found.")
    st.stop()

# Build the base DataFrame (no display yet)
base_df = to_dataframe(rows)

# --- Example tables (manipulate first, display second) ---
tab1, tab2, tab3 = st.tabs(["BW% + 1RM", "Single exercise", "Hard sets summary"])

with tab1:
    df1 = table_bw_and_1rm(base_df)
    st.dataframe(df1, use_container_width=True)

with tab2:
    # let user choose which exercise to view
    all_ex = sorted([e for e in base_df["exercise"].dropna().unique().tolist()])
    chosen = st.selectbox("Exercise", all_ex, index=all_ex.index("Bench Press") if "Bench Press" in all_ex else 0)
    df2 = table_single_exercise(base_df, chosen)
    st.dataframe(df2, use_container_width=True)

with tab3:
    df3 = summarize_hard_sets(base_df, rir_min=1, rir_max=3)
    st.dataframe(df3, use_container_width=True)

# (Optional) raw base table for debugging
with st.expander("Raw flattened data"):
    st.dataframe(base_df, use_container_width=True)
