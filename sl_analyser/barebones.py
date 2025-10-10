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
MAX_PAGES = 1   # for faster demo; increase to fetch all

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

HEADERS = {"User-Agent": USER_AGENT}


# ======================================================
# === FUNCTIONS ========================================
# ======================================================

def fetch_user_id(username: str) -> str:
    """Fetch the user's StrengthLevel page and extract user_id."""
    html = requests.get(f"{BASE_URL}/{username}/workouts", headers=HEADERS).text
    match = re.search(r"window\.prefill\s*=\s*(\[[\s\S]*?\]);", html)
    prefill_json = match.group(1)
    prefill_data = json.loads(prefill_json)
    return prefill_data[0]["request"]["params"]["user_id"]


def fetch_workout_data(user_id: str) -> pd.DataFrame:
    """Fetch limited workout data for speed."""
    all_sets, offset, page_count = [], 0, 0
    session = requests.Session(); session.headers.update(HEADERS)

    params = {
        "user_id": user_id,
        "limit": FETCH_LIMIT,
        "offset": offset,
        "workout.fields": "date,bodyweight,exercises",
        "workoutexercise.fields": "exercise_name,sets",
        "set.fields": "weight,reps,notes,dropset,percentile",
    }
    while True:

        response = session.get(f"{BASE_URL}/api/workouts", params=params).json()
        page = response.get("data", [])
        if not page:
            break

        # Flatten nested JSON
        all_sets += [
            {"date": workout["date"], "exercise": exercise["exercise_name"], **sets}
            for workout in page
            for exercise in workout.get("exercises", [])
            for sets in exercise.get("sets", [])
        ]
        st.write('hi bruv')

        offset += FETCH_LIMIT
        page_count += 1
        if page_count >= MAX_PAGES:
            break
        time.sleep(FETCH_DELAY)

    return pd.json_normalize(all_sets)

def fetch_logic():
    user_id = fetch_user_id(NAME_TO_USERNAME[selected_name])
    df = fetch_workout_data(user_id)
    return df
# ======================================================
# === MAIN =============================================
# ======================================================

st.title("StrengthLevel DATA")
selected_name = st.selectbox("Select person", list(NAME_TO_USERNAME.keys()))

def main_logic():
    df = fetch_logic()
    return df
    

with st.spinner(f"Fetching and rendering {selected_name}'s data..."):
    df = main_logic() 
    st.dataframe(df)

