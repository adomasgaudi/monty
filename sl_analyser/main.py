import streamlit as st
import pandas as pd
from utils import fetch_user_id, fetch_raw_workouts
from variables import NAME_TO_USERNAME
from datetime import datetime

BASE_URL = "https://my.strengthlevel.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}


# ======================================================
# === HELPERS ==========================================
# ======================================================

def format_date(d: str) -> str:
    return datetime.strptime(d, "%Y-%m-%d").strftime("%b-%d")




def calculate_1rm(weight, reps):
    """Use Epley formula (common in SL): 1RM = weight * (1 + reps/30)."""
    if weight and reps:
        return round(weight * (1 + reps / 30), 1)
    return None




def enrich_workouts_with_1rm(raw_data):
    """Add one_rep_max per exercise (based on sets)."""
    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            one_rms = []
            for s in exercise.get("sets", []):
                w, r = s.get("weight"), s.get("reps")
                one_rm = calculate_1rm(w, r)
                if one_rm:
                    s["one_rep_max"] = one_rm
                    one_rms.append(one_rm)
            exercise["one_rep_max"] = max(one_rms) if one_rms else None
    return raw_data




def create_workout_df(all_workouts):
    """Flatten enriched JSON into a clean DataFrame."""
    workout_sets = []
    for workout_day in all_workouts:
        for exercise in workout_day.get("exercises", []):
            for set_info in exercise.get("sets", []):
                if not set_info.get("time") and not set_info.get("distance"):
                    workout_sets.append({
                        "date": format_date(workout_day["date"]),
                        "exercise": exercise["exercise_name"],
                        "weight": set_info.get("weight"),
                        "Reps": set_info.get("reps"),
                        "1RM": set_info.get("one_rep_max"),
                    })
    return pd.json_normalize(workout_sets)




def get_data_from_username(selection):
    username = NAME_TO_USERNAME[selection]
    user_id = fetch_user_id(username, HEADERS, BASE_URL)
    raw_data = fetch_raw_workouts(user_id, HEADERS, BASE_URL)
    enriched_data = enrich_workouts_with_1rm(raw_data)
    return enriched_data




# ======================================================
# === DROPDOWN =============================================
# ======================================================

# 

# 

st.title("StrengthLevel DATA")

selected_name = st.selectbox("Select person", list(NAME_TO_USERNAME.keys()))
raw_data = get_data_from_username(selected_name)

# 

# 

# ======================================================
# === FULL WORKOUT DATA ================================
# ======================================================

# 

# 

with st.expander("📋 Full Workout Data", expanded=False):
    with st.spinner(f"Fetching and rendering {selected_name}'s data..."):
        
        df = create_workout_df(raw_data)
        st.dataframe(df, use_container_width=True, height=640, hide_index=True)

# 

# 

# ======================================================
# === SINGLE EXERCISE ==================================
# ======================================================

# 

# 

exercise_counts = df["exercise"].value_counts().reset_index()
exercise_counts.columns = ["exercise", "count"]

st.subheader("Exercise Selector")

exercise_dict = dict(zip(exercise_counts["exercise"], exercise_counts["count"]))
selected_exercise = st.selectbox("Choose an exercise", list(exercise_dict.keys()))
st.write(f"You selected **{selected_exercise}** — there are **{exercise_dict[selected_exercise]}** sets of this exercise.")

# 

# 

# ======================================================
# === SELECTED EXERCISE DATA ===========================
# ======================================================

# 

# 

df_selected_exercise = df[df["exercise"] == selected_exercise].reset_index(drop=True)

with st.expander(f"📋 Sets for {selected_exercise}", expanded=False):
    df_display = df_selected_exercise.drop(columns=["exercise"], errors="ignore")
    st.dataframe(df_display, use_container_width=True, height=480, hide_index=True)
