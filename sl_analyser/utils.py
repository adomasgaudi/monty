import requests
import json
import re
import time
import streamlit as st

# ======================================================
# === CONFIG ===========================================
# ======================================================

FETCH_LIMIT = 200
FETCH_DELAY = 0.1
MAX_PAGES = 999  # fetch all


# ======================================================
# === FETCH USER ID ====================================
# ======================================================

def fetch_user_id(username: str, headers: dict, base_url: str) -> str:
    """Extract user_id from a user's StrengthLevel workouts page."""
    session = requests.Session()
    session.headers.update(headers)

    html = session.get(f"{base_url}/{username}/workouts").text
    match = re.search(r"window\.prefill\s*=\s*(\[[\s\S]*?\]);", html)

    if not match:
        raise ValueError("Could not find prefill JSON — page structure may have changed.")

    prefill = json.loads(match.group(1))
    return prefill[0]["request"]["params"]["user_id"]


# ======================================================
# === FETCH RAW WORKOUT DATA ===========================
# ======================================================

@st.cache_data(show_spinner=False)
def fetch_raw_workouts(user_id: str, headers: dict, base_url: str):
    """Fetch all workouts (raw JSON from API)."""
    session = requests.Session()
    session.headers.update(headers)

    all_workouts = []
    offset = 0
    progress = st.progress(0.0)

    for _ in range(MAX_PAGES):
        params = {
            "user_id": user_id,
            "limit": FETCH_LIMIT,
            "offset": offset,
            "workout.fields": "date,bodyweight,exercises",
            "workoutexercise.fields": "exercise_name,sets",
            "set.fields": "weight,reps,notes,dropset,percentile",
        }

        resp = session.get(f"{base_url}/api/workouts", params=params).json()
        data = resp.get("data", [])
        if not data:
            break

        all_workouts.extend(data)
        offset += FETCH_LIMIT
        progress.progress(min(1.0, offset / (FETCH_LIMIT * 10)))
        time.sleep(FETCH_DELAY)

    progress.empty()
    return all_workouts
