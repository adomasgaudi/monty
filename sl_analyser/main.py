import streamlit as st
import pandas as pd
from utils import fetch_user_id, fetch_workout_data
from variables import NAME_TO_USERNAME  # your existing dict

# --- Constants ---
BASE_URL = "https://my.strengthlevel.com"
USER_AGENT = "Mozilla/5.0"
HEADERS = {"User-Agent": USER_AGENT}


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
        df = fetch_workout_data(user_id, HEADERS, BASE_URL)
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
