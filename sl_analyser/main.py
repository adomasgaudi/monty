import streamlit as st
import pandas as pd
from utils import fetch_user_id, fetch_raw_workouts
from variables import NAME_TO_USERNAME, EXERCISE_DATA
from datetime import datetime

BASE_URL = "https://my.strengthlevel.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}


# ======================================================
# === HELPERS ==========================================
# ======================================================

def format_date(d: str) -> str:
    return datetime.strptime(d, "%Y-%m-%d").strftime("%b-%d")


def epley3_reps(w: float, w_rec: float, w_i: float) -> float:
    """Estimate reps given weight, 1RM, and internal load."""
    return (100 * (w_rec + w_i)) / (3.33 * (w + w_i)) - 29


def epley3_record(w: float, reps: float, w_i: float) -> float:
    """Estimate 1RM given working weight, reps, and internal load."""
    if w is None or reps is None or w_i is None:
        return None
    try:
        return round((3.33 * (w + w_i) * (reps + 29)) / 100 - w_i, 1)
    except ZeroDivisionError:
        return None


def epley3_weight(w_rec: float, reps: float, w_i: float) -> float:
    """Estimate working weight given 1RM, target reps, and internal load."""
    if w_rec is None or reps is None or w_i is None:
        return None
    try:
        return round((100 * (w_rec + w_i)) / (3.33 * (reps + 29)) - w_i, 1)
    except ZeroDivisionError:
        return None


# ======================================================
# === DATA ENRICHMENT ==================================
# ======================================================

def enrich_workouts_with_bodyweight_load(raw_data):
    """Attach bodyweight contribution and equipment weight to each exercise."""
    for workout in raw_data:
        bodyweight = workout.get("bodyweight", 0)
        for exercise in workout.get("exercises", []):
            name = exercise.get("exercise_name", "").strip()
            data = EXERCISE_DATA.get(name, {"bwp": 0, "eq_w": 0})

            bwp = data.get("bwp") or 0.0
            eq_w = data.get("eq_w") or 0.0
            bw_load = round(bodyweight * bwp, 2)
            w_i = bw_load + eq_w

            exercise["bodyweight_p"] = bwp
            exercise["bodyweight_load"] = bw_load
            exercise["equipment_weight"] = eq_w
            exercise["internal_load"] = round(w_i, 2)
    return raw_data


def enrich_workouts_with_1rm(raw_data):
    """Compute per-set and per-exercise 1RM using modified Epley3 formula."""
    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            one_rms = []
            w_i = exercise.get("internal_load", 0.0)
            for s in exercise.get("sets", []):
                w = s.get("weight")
                r = s.get("reps")
                if w is not None and r is not None:
                    one_rm = epley3_record(w, r, w_i)
                    if one_rm is not None:
                        s["one_rep_max"] = one_rm
                        one_rms.append(one_rm)
            exercise["one_rep_max"] = max(one_rms) if one_rms else None
    return raw_data


# ======================================================
# === DATAFRAME CREATION ===============================
# ======================================================

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
                        "1RM": exercise.get("one_rep_max"),
                    })
    return pd.json_normalize(workout_sets)


def get_data_from_username(selection):
    username = NAME_TO_USERNAME[selection]
    user_id = fetch_user_id(username, HEADERS, BASE_URL)
    raw_data = fetch_raw_workouts(user_id, HEADERS, BASE_URL)

    enriched = enrich_workouts_with_bodyweight_load(raw_data)
    enriched = enrich_workouts_with_1rm(enriched)
    return enriched


# ======================================================
# === UI: SELECTION ====================================
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
