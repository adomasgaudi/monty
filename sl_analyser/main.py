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

BASE_URL = "https://my.strengthlevel.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}


# ------------------------------------------------------
# MOBILE STYLING
# ------------------------------------------------------
st.write("v.b0.7b")
st.markdown("""
<style>
div[data-baseweb="select"] > div {
    width: fit-content !important;
    min-width: 180px !important;
    max-width: 90vw !important;
}
.stSelectbox { padding-left: 5px; padding-right: 5px; }
.stSelectbox > div > div { display: inline-block !important; }
[data-testid="stFormSubmitButton"], .stButton button {
    width: fit-content !important;
    padding: 0.4rem 1rem !important;
}
</style>
""", unsafe_allow_html=True)


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

st.title("StrengthLevel DATA")

df = create_workout_df(raw_data)


# ------------------------------------------------------
# SINGLE EXERCISE VIEW
# ------------------------------------------------------
exercise_counts = df["exercise"].value_counts().reset_index()
exercise_counts.columns = ["exercise", "count"]

selected_exercise = st.selectbox("Choose an exercise", exercise_counts["exercise"])

st.subheader("Training Sets")
df_selected = df[df["exercise"] == selected_exercise]
st.dataframe(df_selected.drop(columns=["exercise"]), use_container_width=True, hide_index=True, height=480)


# ------------------------------------------------------
# WEEKLY SUMMARY (NO week_start column)
# ------------------------------------------------------
st.header("📊 Weekly Volume Summary")

weekly_rows = []
for w in raw_data:
    raw_date = w.get("date")
    if not raw_date:
        continue

    d = datetime.strptime(raw_date, "%Y-%m-%d")
    year, week, day = d.isocalendar()
    week_label = f"{year}-W{week:02d}"

    for ex in w.get("exercises", []):
        weekly_rows.append({
            "week": week_label,
            "exercise": ex.get("exercise_name", ""),
            "Relative Volume": ex.get("volume_relative", 0),
            "Heavy Volume": ex.get("heavy_sets", 0),
            "Hard Sets": ex.get("hard_sets", 0),
        })

df_weekly = pd.DataFrame(weekly_rows)

df_weekly_summary = (
    df_weekly.groupby(["week", "exercise"], as_index=False)
    .agg({
        "Relative Volume": "sum",
        "Heavy Volume": "sum",
        "Hard Sets": "sum",
    })
    .sort_values("week", ascending=False)
)

st.dataframe(df_weekly_summary, use_container_width=True, hide_index=True, height=480)


# --- weekly plot ---
exercises_available = sorted(df_weekly_summary["exercise"].unique())
selected_ex_hist = st.selectbox("Select exercise for weekly histogram", exercises_available)

df_plot = df_weekly_summary[df_weekly_summary["exercise"] == selected_ex_hist].copy()


def iso_week_to_date(week_str):
    year_str, wk_str = week_str.split("-W")
    return datetime.fromisocalendar(int(year_str), int(wk_str), 1)


df_plot["plot_date"] = df_plot["week"].apply(iso_week_to_date)
df_plot["plot_date"] += timedelta(days=1)  # spacing

cutoff = datetime.now() - timedelta(weeks=16)
df_plot = df_plot[df_plot["plot_date"] >= cutoff]
df_plot = df_plot.sort_values("plot_date")

if not df_plot.empty:
    import plotly.graph_objects as go

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df_plot["plot_date"],
        y=df_plot["Relative Volume"],
        name="Relative Volume",
        marker_color="#9bafd9",
        opacity=0.8,
        yaxis="y1"
    ))

    fig.add_trace(go.Bar(
        x=df_plot["plot_date"],
        y=df_plot["Heavy Volume"],
        name="Heavy Volume",
        marker_color="#d9534f",
        opacity=0.8,
        yaxis="y2"
    ))

    fig.add_trace(go.Bar(
        x=df_plot["plot_date"],
        y=df_plot["Hard Sets"],
        name="Hard Sets",
        marker_color="#5cb85c",
        opacity=0.8,
        yaxis="y3"
    ))

    fig.update_layout(
        title=f"{selected_ex_hist} — Weekly Training Metrics (Last 4 Months)",
        barmode="group",
        xaxis=dict(
            domain=[0.0, 0.82],
            title="Week",
            tickformat="%b %d",
            showgrid=False
        ),
        yaxis=dict(
            title=dict(text="Relative Volume", font=dict(color="#9bafd9")),
            tickfont=dict(color="#9bafd9"),
        ),
        yaxis2=dict(
            title=dict(text="Heavy Volume", font=dict(color="#d9534f")),
            tickfont=dict(color="#d9534f"),
            overlaying="y",
            side="right",
            position=0.82
        ),
        yaxis3=dict(
            title=dict(text="Hard Sets", font=dict(color="#5cb85c")),
            tickfont=dict(color="#5cb85c"),
            overlaying="y",
            side="right",
            position=0.90
        ),
        legend=dict(x=0.02, y=1.1, orientation="h"),
        margin=dict(l=60, r=120, t=60, b=40),
        template="plotly_white",
    )

    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No weekly data available for this exercise.")


# ------------------------------------------------------
# EXERCISE HISTORY (with zero-days)
# ------------------------------------------------------
st.header("🏋️ Exercise History Overview")

all_exercises = sorted({
    ex.get("exercise_name", "")
    for w in raw_data
    for ex in w.get("exercises", [])
    if ex.get("exercise_name")
})

selected_history = st.selectbox("Exercise history:", all_exercises)

history_rows = []
for w in raw_data:
    raw_date = w["date"]
    formatted = format_date(raw_date)

    todays = [ex for ex in w["exercises"] if ex["exercise_name"] == selected_history]

    if todays:
        ex = todays[0]
        history_rows.append({
            "raw_date": raw_date,
            "date": formatted,
            "Relative Volume": ex.get("volume_relative", 0),
            "Heavy Volume": ex.get("heavy_sets", 0),
            "Hard Sets": ex.get("hard_sets", 0),
        })
    else:
        history_rows.append({
            "raw_date": raw_date,
            "date": formatted,
            "Relative Volume": 0,
            "Heavy Volume": 0,
            "Hard Sets": 0,
        })

df_history = (
    pd.DataFrame(history_rows)
    .sort_values("raw_date", ascending=False)
    .drop(columns=["raw_date"])
)

st.dataframe(df_history, use_container_width=True, hide_index=True, height=480)


# ------------------------------------------------------
# CLEAN DISPLAY: ONE TABLE PER DAY, PER EXERCISE
# ------------------------------------------------------
st.title("Workout History (Clean Tables)")

for workout_day in raw_data:
    date_str = format_date(workout_day["date"])
    st.header(f"📅 {date_str}")

    for ex in workout_day.get("exercises", []):
        ex_name = ex.get("exercise_name", "")
        st.subheader(ex_name)

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
            st.dataframe(df_ex, use_container_width=True, hide_index=True, height=220)
        else:
            st.info("No strength sets logged.")


# ------------------------------------------------------
# QUICK TABLE: ALL SETS OF SELECTED EXERCISE
# ------------------------------------------------------
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
