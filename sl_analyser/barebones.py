# ======================================================
# === IMPORTS & CONFIGURATION ==========================
# ======================================================

import streamlit as st
import requests
import pandas as pd
import json
import re
import time

BASE_URL = "https://my.strengthlevel.com"
USER_AGENT = "Mozilla/5.0"
FETCH_LIMIT = 200
FETCH_DELAY = 0.1
MAX_PAGES = 999  # fetch all

HEADERS = {"User-Agent": USER_AGENT}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

NAME_TO_USERNAME = {
    "Adomas": "adomasgaudi",
    "Sandra": "sandrakri",
    "Pocius": "jpociuss",
    "Johanness": "johannesschut",
    "dzuljeta": "dzuljeta",
    "mantas": "mantasp",
    "kristina": "andromeda94",
    "andrius": "andriusp",
}

# ======================================================
# === FUNCTIONS ========================================
# ======================================================

@st.cache_data(show_spinner=False)
def fetch_user_id(username: str) -> str:
    """Extract user_id from user’s workouts page."""
    html = SESSION.get(f"{BASE_URL}/{username}/workouts").text
    match = re.search(r"window\.prefill\s*=\s*(\[[\s\S]*?\]);", html)
    prefill = json.loads(match.group(1))
    return prefill[0]["request"]["params"]["user_id"]


@st.cache_data(show_spinner=False)
def fetch_workout_data(user_id: str) -> pd.DataFrame:
    """Fetch all workouts quickly using persistent session."""
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
        resp = SESSION.get(f"{BASE_URL}/api/workouts", params=params).json()
        data = resp.get("data", [])
        if not data:
            break
        
        
        
        
        for workout_day in data:
            for exercise in workout_day.get("exercises", []): 
                for set_info in exercise.get("sets", []): 
                    # st.write("set_info")
                    # st.write(set_info)
                    workout_sets.append({
                        "date": workout_day["date"],     
                        "exercise": exercise["exercise_name"],
                        **set_info                          
                    })
                    # st.write(workout_sets)
                    
                    
                    
        offset += FETCH_LIMIT
        progress.progress(min(1.0, offset / (FETCH_LIMIT * 10)))  # simple fake progress
        time.sleep(FETCH_DELAY)
    progress.empty()
    return pd.json_normalize(workout_sets)

# ======================================================
# === MAIN =============================================
# ======================================================

st.title("StrengthLevel DATA")

selected_name = st.selectbox("Select person", list(NAME_TO_USERNAME.keys()))
username = NAME_TO_USERNAME[selected_name]

with st.spinner(f"Fetching and rendering {selected_name}'s data..."):
    user_id = fetch_user_id(username)
    df = fetch_workout_data(user_id)
    st.dataframe(df, use_container_width=True, height=640)

