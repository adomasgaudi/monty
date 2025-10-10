import requests
import json
import re
import pandas as pd
import time
from datetime import datetime
import streamlit as st


# ======================================================
# === CONFIG ===========================================
# ======================================================

FETCH_LIMIT = 200
FETCH_DELAY = 0.1
MAX_PAGES = 999  # fetch all


# ======================================================
# === HELPERS ==========================================
# ======================================================

def format_date(d: str) -> str:
    """Format YYYY-MM-DD into 'Mon-DD'."""
    return datetime.strptime(d, "%Y-%m-%d").strftime("%b-%d")


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
# === FETCH WORKOUT DATA ===============================
# ======================================================

@st.cache_data(show_spinner=False)
def fetch_workout_data(user_id: str, headers: dict, base_url: str) -> pd.DataFrame:
    """Fetch all workouts quickly using persistent session."""
    session = requests.Session()
    session.headers.update(headers)

    workout_sets, offset = [], 0
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
        all_workouts = resp.get("data", [])
        if not all_workouts:
            break

        for workout_day in all_workouts:
            for exercise in workout_day.get("exercises", []):
                for set_info in exercise.get("sets", []):
                    if not set_info.get("time") and not set_info.get("distance"):
                        workout_sets.append({
                            "date": format_date(workout_day["date"]),
                            "exercise": exercise["exercise_name"],
                            "weight": set_info.get("weight"),
                            "Reps": set_info.get("reps")
                        })

        offset += FETCH_LIMIT
        progress.progress(min(1.0, offset / (FETCH_LIMIT * 10)))
        time.sleep(FETCH_DELAY)

    progress.empty()
    return pd.json_normalize(workout_sets)
