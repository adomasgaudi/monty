import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import requests
import streamlit as st
from variables import NAME_TO_USERNAME, BW_PCT_RAW


# ======================================================
# === CONFIGURATION ====================================
# ======================================================

APP_TITLE = "StrengthLevel DATA"
API_BASE_URL = "https://my.strengthlevel.com/api/workouts"
PAGE_BASE_URL = "https://my.strengthlevel.com"
USER_AGENT = "Mozilla/5.0"
FETCH_LIMIT = 200
FETCH_DELAY = 0.15  # seconds between API pages
MIME_CSV = "text/csv"

_BW_KEYMAP = {k.strip().lower(): v for k, v in BW_PCT_RAW.items()}


# ======================================================
# === INITIALIZATION ===================================
# ======================================================

st.set_page_config(page_title=APP_TITLE, layout="centered")
st.title(APP_TITLE)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


# ======================================================
# === UTILITY FUNCTIONS ================================
# ======================================================

def _norm(s: Optional[str]) -> str:
    """Normalize a string for case-insensitive lookups."""
    return (s or "").strip().lower()


def _fetch_html(url: str) -> str:
    """Fetch raw HTML from a page with proper headers and error handling."""
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        st.error(f"Failed to fetch {url}: {e}")
        log.exception("Fetch error")
        st.stop()


def _extract_user_id(html: str) -> str:
    """Extract StrengthLevel user_id from embedded JSON (window.prefill)."""
    match = re.search(r"window\.prefill\s*=\s*(\[[\s\S]*?\]);", html)
    if not match:
        st.error("Could not find window.prefill JSON; page structure changed?")
        st.stop()

    try:
        prefill = json.loads(match.group(1))
    except Exception:
        st.error("Failed to parse window.prefill JSON.")
        st.stop()

    for blob in prefill:
        req = blob.get("request", {})
        if req.get("url") == "/api/workouts":
            params = req.get("params", {})
            user_id = params.get("user_id")
            if user_id:
                return user_id

    st.error("Could not extract user_id from page JSON.")
    st.stop()


def _fetch_workouts(user_id: str) -> List[Dict[str, Any]]:
    """Fetch paginated StrengthLevel workouts for a given user_id."""
    headers = {"User-Agent": USER_AGENT}
    offset = 0
    all_rows: List[Dict[str, Any]] = []
    progress = st.progress(0.0)
    total_expected: Optional[int] = None

    while True:
        params = {
            "user_id": user_id,
            "workout.fields": "date,bodyweight,total,exercises,timezone,timezone_offset_mins",
            "workoutexercise.fields": "exercise_name,exercise_name_url,sets,total,is_custom_exercise",
            "set.fields": "weight,reps,notes,dropset,percentile",
            "limit": FETCH_LIMIT,
            "offset": offset,
        }

        try:
            response = requests.get(API_BASE_URL, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as e:
            st.error(f"API request failed at offset {offset}: {e}")
            log.exception("API request failed")
            break
        except ValueError:
            st.error(f"Non-JSON response at offset {offset}.")
            break

        data = payload.get("data", [])
        meta = payload.get("meta", {})
        if total_expected is None:
            total_expected = meta.get("count", 1)

        if not data:
            break

        all_rows.extend(_flatten_workouts(data))
        offset += FETCH_LIMIT

        if total_expected:
            progress.progress(min(1.0, len(all_rows) / float(total_expected)))

        time.sleep(FETCH_DELAY)
        if len(data) < FETCH_LIMIT:
            break

    if not all_rows:
        st.warning("No workout data found.")
        st.stop()

    return all_rows


def _flatten_workouts(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten nested workout JSON into row-level dicts."""
    rows: List[Dict[str, Any]] = []
    for workout in data:
        w_id = workout.get("id")
        date = workout.get("date")
        bodyweight = workout.get("bodyweight")
        exercises = workout.get("exercises") or []

        if not exercises:
            rows.append(_blank_row(w_id, date, bodyweight))
            continue

        for ex in exercises:
            ex_name = ex.get("exercise_name", "")
            sets = ex.get("sets") or []
            if not sets:
                rows.append(_blank_row(w_id, date, bodyweight, ex_name))
                continue

            for s in sets:
                rows.append({
                    "workout_id": w_id,
                    "date": date,
                    "bodyweight": bodyweight,
                    "exercise": ex_name,
                    "weight": s.get("weight"),
                    "reps": s.get("reps"),
                    "notes": s.get("notes", ""),
                    "dropset": s.get("dropset", False),
                    "percentile": s.get("percentile"),
                })
    return rows


def _blank_row(w_id: Any, date: Any, bodyweight: Any, exercise: str = "") -> Dict[str, Any]:
    """Return a placeholder row for missing exercise data."""
    return {
        "workout_id": w_id,
        "date": date,
        "bodyweight": bodyweight,
        "exercise": exercise,
        "weight": None,
        "reps": None,
        "notes": "",
        "dropset": False,
        "percentile": None,
    }


# ================================================z======
# === DATA PROCESSING ==================================
# ======================================================

def _enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Add computed columns: bodyweight %, internal weight, and estimated 1RM."""
    for col in ["weight", "reps", "percentile", "bodyweight"]:
        df[col] = pd.to_numeric(df[col], errors="ignore")

    df["bw_pct"] = df["exercise"].map(lambda x: _BW_KEYMAP.get(_norm(x)))
    df["internal_weight"] = df["bodyweight"] * df["bw_pct"]

    df["est_1RM"] = df.apply(_epley3, axis=1).round(1)

    # Reorder columns for readability
    preferred = [
        "date", "bodyweight", "bw_pct", "internal_weight",
        "exercise", "weight", "reps", "est_1RM",
        "notes", "dropset", "percentile",
    ]
    df = df[[c for c in preferred if c in df.columns] +
            [c for c in df.columns if c not in preferred]]

    if "date" in df.columns:
        parsed = pd.to_datetime(df["date"], errors="coerce")
        df["date"] = parsed.dt.strftime("%b-%d").fillna(df["date"])

    return df


def _epley3(row: pd.Series) -> float:
    """Epley3 formula for estimated one-rep max."""
    reps = row.get("reps")
    wi = row.get("internal_weight")
    x = row.get("weight")

    if pd.isna(reps) or reps <= 0 or pd.isna(wi):
        return np.nan
    x = 0.0 if pd.isna(x) else float(x)
    return ((float(reps) + 29.0) * 3.33 * (x + float(wi))) / 100.0 - float(wi)


# ======================================================
# === UI COMPONENTS ====================================
# ======================================================

def _render_dataframe(df: pd.DataFrame) -> None:
    """Render the dataframe in Streamlit with appropriate settings."""
    hidden_cols = ["bodyweight", "internal_weight"]
    display_df = df.drop(columns=hidden_cols, errors="ignore")

    dataframe_params = {
        "data": display_df,
        "use_container_width": True,
        "height": 640,
        "hide_index": True,
    }
    st.dataframe(**dataframe_params)
    st.caption(f"Total rows: {len(df)}")


def _render_download_button(df: pd.DataFrame, username: str) -> None:
    """Render a download button for exporting the data as CSV."""
    download_params = {
        "data": df.to_csv(index=False).encode("utf-8-sig"),
        "file_name": f"{username}_sl_workouts.csv",
        "mime": MIME_CSV,
    }
    st.download_button("Download CSV", **download_params)


# ======================================================
# === MAIN EXECUTION FLOW ==============================
# ======================================================

def main() -> None:
    names = list(NAME_TO_USERNAME.keys())
    default_index = names.index("dzuljeta") if "dzuljeta" in names else 0

    selected_name = st.selectbox("Select person", names, index=default_index)
    username = NAME_TO_USERNAME[selected_name]

    # Only refetch when user changes selection
    if st.session_state.get("last_selected") == selected_name:
        st.info("Select a different person to fetch new data.")
        return

    st.session_state.last_selected = selected_name

    base_url = f"{PAGE_BASE_URL}/{username}/workouts"
    html = _fetch_html(base_url)
    user_id = _extract_user_id(html)

    log.info("Fetching workouts for %s (user_id=%s)", username, user_id)
    rows = _fetch_workouts(user_id)
    st.write("---")
    st.write(rows)
    df = pd.DataFrame(rows)
    df = _enrich_dataframe(df)

    _render_dataframe(df)
    _render_download_button(df, username)


# ======================================================
# === ENTRY POINT ======================================
# ======================================================

if __name__ == "__main__":
    main()
