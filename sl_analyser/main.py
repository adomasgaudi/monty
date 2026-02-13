import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from utils import fetch_user_id, fetch_raw_workouts
from variables import NAME_TO_USERNAME
from enrich import (
    enrich_workouts_with_bodyweight_load,
    enrich_workouts_with_1rm,
    enrich_workouts_with_rir,
    enrich_workouts_with_hard_sets,
    enrich_workouts_with_volume,
    enrich_workouts_with_heavy_volume,
    format_date,
)
from styles import load_styles

BASE_URL = "https://my.strengthlevel.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}


# ------------------------------------------------------
# VERSION + STYLES
# ------------------------------------------------------
st.write("v.b0.9")
st.markdown(load_styles(), unsafe_allow_html=True)

# ------------------------------------------------------
# SIMPLE PAGE SWITCH USING SESSION STATE
# ------------------------------------------------------
if "show_hello" not in st.session_state:
    st.session_state.show_hello = False

col1, col2 = st.columns(2)
with col1:
    if st.button("Go to Hello Page"):
        st.session_state.show_hello = True
with col2:
    if st.button("Go Back"):
        st.session_state.show_hello = False

# If Hello mode is active — show ONLY Hello world and stop the app
if st.session_state.show_hello:
    st.title("exercises page")
    
    st.stop()


# ------------------------------------------------------
# DATAFRAME CREATION
# ------------------------------------------------------
def create_workout_df(all_workouts):
    rows = []
    for workout_day in all_workouts:
        for ex in workout_day.get("exercises", []):
            for s in ex.get("sets", []):
                if s.get("time") or s.get("distance"):
                    continue
                rows.append({
                    "date": format_date(workout_day["date"]),
                    "exercise": ex["exercise_name"],
                    "weight": s.get("weight"),
                    "Reps": s.get("reps"),
                    "1RM": ex.get("one_rep_max"),
                })
    return pd.DataFrame(rows)


def get_data_from_username(selection):
    username = NAME_TO_USERNAME[selection]
    user_id = fetch_user_id(username, HEADERS, BASE_URL)
    raw = fetch_raw_workouts(user_id, HEADERS, BASE_URL)

    raw = enrich_workouts_with_bodyweight_load(raw)
    raw = enrich_workouts_with_1rm(raw)
    raw = enrich_workouts_with_rir(raw)
    raw = enrich_workouts_with_hard_sets(raw)
    raw = enrich_workouts_with_volume(raw)
    raw = enrich_workouts_with_heavy_volume(raw)

    return raw


# ------------------------------------------------------
# UI SETUP
# ------------------------------------------------------
selected_name = st.selectbox("Select person", list(NAME_TO_USERNAME.keys()))
raw_data = get_data_from_username(selected_name)

df = create_workout_df(raw_data)
st.write(df)

# ------------------------------------------------------
# WORKOUT HISTORY (WITH CUSTOM STYLING)
# ------------------------------------------------------
for workout_day in raw_data:
    date_str = format_date(workout_day["date"])
    st.divider()

    st.markdown(
        f"<h3 class='subheader-date'>📅 {date_str}</h3>",
        unsafe_allow_html=True
    )

    for ex in workout_day.get("exercises", []):
        ex_name = ex.get("exercise_name", "")
        # st.write(ex)
        st.markdown(
            f"{ex_name}. :orange-badge[sets: {5*4}]"
        )
        

        rows = []
        for s in ex.get("sets", []):
            if s.get("time") or s.get("distance"):
                continue
            rows.append({
                "Weight (kg)": s.get("weight"),
                "Reps": s.get("reps"),
                "1RM (kg)": ex.get("one_rep_max"),
            })

        if rows:
            df_ex = pd.DataFrame(rows)
            st.dataframe(
                df_ex,
                use_container_width=True,
                hide_index=True,
                height="auto"
            )
        else:
            st.info("No strength sets logged.")


# ------------------------------------------------------
# QUICK TABLE: ALL SETS OF SELECTED EXERCISE
# ------------------------------------------------------
exercise_counts = df["exercise"].value_counts().reset_index()
exercise_counts.columns = ["exercise", "count"]

exercise_dict = dict(zip(exercise_counts["exercise"], exercise_counts["count"]))
selected_exercise = st.selectbox("Choose an exercise", list(exercise_dict.keys()))

df_selected_exercise = df[df["exercise"] == selected_exercise].reset_index(drop=True)

st.write("table 1")
st.dataframe(
    df_selected_exercise.drop(columns=["exercise"], errors="ignore"),
    use_container_width=True,
    hide_index=True,
    height=480
)
