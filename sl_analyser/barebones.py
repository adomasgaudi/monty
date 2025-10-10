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
    pattern = r"window\.prefill\s*=\s*(\[[\s\S]*?\]);"
    myworkout_json = re.search(pattern, html).group(1)
    myworkout_data = json.loads(myworkout_json)
    # ---------------
    st.write("------")
    st.write(myworkout_data)
    st.write("------")
    st.write(myworkout_data[0]["request"]["params"])
    return myworkout_data[0]["request"]["params"]["user_id"]

def fetch_workout_data(user_id: str) -> pd.DataFrame:
    rows, offset = [], 0
    session = requests.Session(); session.headers.update(HEADERS)

    while True:
        params = {
            "user_id": user_id, "limit": FETCH_LIMIT, "offset": offset,
            "workout.fields": "date,bodyweight,exercises",
            "workoutexercise.fields": "exercise_name,sets",
            "set.fields": "weight,reps,notes",
        }
        page = session.get(f"{BASE_URL}/api/workouts", params=params).json().get("data")
        if not page:
            break

        rows += [
            {"date": w["date"], "exercise": ex["exercise_name"], **st}
            for w in page for ex in w.get("exercises", []) for st in ex.get("sets", [])
        ]
        offset += FETCH_LIMIT
        time.sleep(FETCH_DELAY)

    return pd.json_normalize(rows)


# ======================================================
# === MAIN =============================================
# ======================================================

st.title("StrengthLevel DATA")
st_selected_name = st.selectbox("Select", list(NAME_TO_USERNAME.keys()))

def fetch_workout_df():
    user_id = fetch_user_id(NAME_TO_USERNAME[st_selected_name])
    df = fetch_workout_data(user_id)
    return df

st.dataframe(fetch_workout_df())

