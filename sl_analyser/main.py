# ======================================================
# === IMPORTS & CONFIGURATION ==========================
# ======================================================

import streamlit as st
import requests
import pandas as pd
import json
import re
import time
from datetime import datetime
from utils import fetch_user_id
from variables import NAME_TO_USERNAME  # assumes you have a variables.py file with the dict

# --- Constants ---
BASE_URL = "https://my.strengthlevel.com"
USER_AGENT = "Mozilla/5.0"
FETCH_LIMIT = 200
FETCH_DELAY = 0.1
MAX_PAGES = 999  # fetch all

HEADERS = {"User-Agent": USER_AGENT}


# ======================================================
# === UTILS ============================================
# ======================================================

def format_date(d: str) -> str:
    """Format YYYY-MM-DD into 'Mon-DD'."""
    return datetime.strptime(d, "%Y-%m-%d").strftime("%b-%d")


# ======================================================
# === FETCH WORKOUT DATA ===============================
# ======================================================

@st.cache_data(show_spinner=False)
def fetch_workout_data(user_id: str) -> pd.DataFrame:
    """Fetch all workouts quickly using a local session."""
    session = requests.Session()
    session.headers.update(HEADERS)

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

        resp = session.get(f"{BASE_URL}/api/workouts", params=params).json()
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


# ======================================================
# === MAIN =============================================
# ======================================================

st.title("StrengthLevel DATA")

selected_name = st.selectbox("Select person", list(NAME_TO_USERNAME.keys()))
username = NAME_TO_USERNAME[selected_name]

# --- Main Data Table ---
with st.expander("📋 Full Workout Data", expanded=False):
    with st.spinner(f"Fetching and rendering {selected_name}'s data..."):
        user_id = fetch_user_id(username, HEADERS, BASE_URL)
        df = fetch_workout_data(user_id)
        st.dataframe(df, use_container_width=True, height=640, hide_index=True)

# --- Exercise Frequency Table ---
exercise_counts = df["exercise"].value_counts().reset_index()
exercise_counts.columns = ["exercise", "count"]

st.subheader("Exercise Selector")

exercise_dict = dict(zip(exercise_counts["exercise"], exercise_counts["count"]))
selected_exercise = st.selectbox("Choose an exercise", list(exercise_dict.keys()))
st.write(f"You selected **{selected_exercise}** — there are **{exercise_dict[selected_exercise]}** sets of this exercise.")

# --- Filtered Table (Collapsible) ---
df_selected_exercise = df[df["exercise"] == selected_exercise].reset_index(drop=True)

with st.expander(f"📋 Sets for {selected_exercise}", expanded=False):
    df_display = df_selected_exercise.drop(columns=["exercise"], errors="ignore")
    st.dataframe(df_display, use_container_width=True, height=480, hide_index=True)
