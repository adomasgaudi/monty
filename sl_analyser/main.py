import streamlit as st
import pandas as pd
from utils import fetch_user_id, fetch_raw_workouts
from variables import NAME_TO_USERNAME, EXERCISE_DATA
from datetime import datetime, timedelta
from enrich import enrich_workouts_with_bodyweight_load, enrich_workouts_with_1rm, enrich_workouts_with_rir, enrich_workouts_with_hard_sets, enrich_workouts_with_volume, enrich_workouts_with_heavy_volume, format_date

BASE_URL = "https://my.strengthlevel.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}


# --- Mobile-friendly styling ---
st.write("v.b0.2")
st.markdown(
"""
<style>
/* Make select boxes shrink to content width instead of 100% */
div[data-baseweb="select"] > div {
    width: fit-content !important;
    min-width: 180px !important;
    max-width: 90vw !important; /* prevent overflow on phones */
}

/* Add some margin so it doesn’t hug the edges */
.stSelectbox {
    padding-left: 5px;
    padding-right: 5px;
}

/* Make Streamlit widgets not stretch full width */
.stSelectbox > div > div {
    display: inline-block !important;
}

/* Center buttons and inputs better on narrow screens */
[data-testid="stFormSubmitButton"], .stButton button {
    width: fit-content !important;
    padding: 0.4rem 1rem !important;
}
</style>
""", unsafe_allow_html=True
)




# ======================================================
# === DATAFRAME CREATION ===============================
# ======================================================

def create_workout_df(all_workouts):
    """Flatten enriched JSON into a clean DataFrame, adding empty row between days."""
    workout_sets = []
    for i, workout_day in enumerate(all_workouts):
        day_rows = []
        for exercise in workout_day.get("exercises", []):
            for set_info in exercise.get("sets", []):
                if not set_info.get("time") and not set_info.get("distance"):
                    day_rows.append({
                        "date": format_date(workout_day["date"]),
                        "exercise": exercise["exercise_name"],
                        "weight": set_info.get("weight"),
                        "Reps": set_info.get("reps"),
                        "1RM": exercise.get("one_rep_max"),
                    })
        workout_sets.extend(day_rows)
        if i < len(all_workouts) - 1:
            workout_sets.append({"date": "", "exercise": "", "weight": None, "Reps": None, "1RM": None})
    return pd.json_normalize(workout_sets)

def get_data_from_username(selection):
    username = NAME_TO_USERNAME[selection]
    user_id = fetch_user_id(username, HEADERS, BASE_URL)
    raw_data = fetch_raw_workouts(user_id, HEADERS, BASE_URL)

    enriched = enrich_workouts_with_bodyweight_load(raw_data)
    enriched = enrich_workouts_with_1rm(enriched)
    enriched = enrich_workouts_with_rir(enriched)
    enriched = enrich_workouts_with_hard_sets(enriched)  # 👈 new step
    enriched = enrich_workouts_with_volume(enriched)
    enriched = enrich_workouts_with_heavy_volume(enriched)
    st.write("enriched!")
    return enriched


# ======================================================
# === UI: SELECTION ====================================
# ======================================================

selected_name = st.selectbox("Select person", list(NAME_TO_USERNAME.keys()))
raw_data = get_data_from_username(selected_name)
st.write("raw_data")
st.write(raw_data)
st.title("StrengthLevel DATA")

# ======================================================
# === FULL WORKOUT DATA ================================
# ======================================================

with st.spinner(f"Fetching and rendering {selected_name}'s data..."):
    df = create_workout_df(raw_data)

        # ======================================================
        # === EXERCISE ACTIVITY (LAST 4 MONTHS) ================
        # ======================================================
        
# ======================================================
# === SINGLE EXERCISE ==================================
# ======================================================

exercise_counts = df["exercise"].value_counts().reset_index()
exercise_counts.columns = ["exercise", "count"]

exercise_dict = dict(zip(exercise_counts["exercise"], exercise_counts["count"]))
selected_exercise = st.selectbox("Choose an exercise", list(exercise_dict.keys()))

df_selected_exercise = df[df["exercise"] == selected_exercise].reset_index(drop=True)
st.write("table 1")
st.dataframe(df_selected_exercise.drop(columns=["exercise"], errors="ignore"),
                use_container_width=True, height=480, hide_index=True)



# ======================================================
# === DAILY VOLUME SUMMARY =============================
# ======================================================
st.write("table 2")
summary_rows = []
for i, workout_day in enumerate(raw_data):
    date_str = format_date(workout_day["date"])
    day_rows = []
    for exercise in workout_day.get("exercises", []):
        day_rows.append({
            "date": date_str,
            "exercise": exercise.get("exercise_name", ""),
            "Relative Volume": exercise.get("volume_relative", 0),
            "Heavy Volume": exercise.get("heavy_sets", 0),
            "Hard Sets": exercise.get("hard_sets", 0),  # 👈 new column
        })
    summary_rows.extend(day_rows)
    if i < len(raw_data) - 1:
        summary_rows.append({"date": "", "exercise": "", "Relative Volume": None, "Heavy Volume": None, "Hard Sets": None})

if summary_rows:
    df_summary = pd.DataFrame(summary_rows)
    st.dataframe(df_summary, use_container_width=True, hide_index=True, height=480)
else:
    st.info("No volume data available yet.")

# # ======================================================
# === WEEKLY VOLUME SUMMARY + HISTOGRAM ================
# ======================================================

weekly_rows = []
st.write("table 3")
# Flatten all exercises with metrics and week labels
for workout_day in raw_data:
    raw_date = workout_day.get("date")
    if not raw_date:
        continue
    date_obj = datetime.strptime(raw_date, "%Y-%m-%d")
    iso_year, iso_week, _ = date_obj.isocalendar()
    week_label = f"{iso_year}-W{iso_week:02d}"

    for exercise in workout_day.get("exercises", []):
        weekly_rows.append({
            "week": week_label,
            "week_start": date_obj - timedelta(days=date_obj.weekday()),  # Monday of that week
            "exercise": exercise.get("exercise_name", ""),
            "Relative Volume": exercise.get("volume_relative", 0),
            "Heavy Volume": exercise.get("heavy_sets", 0),
            "Hard Sets": exercise.get("hard_sets", 0),
        })

if weekly_rows:
    df_weekly = pd.DataFrame(weekly_rows)

    # --- Aggregate per week, week_start & exercise ---
    df_weekly_summary = (
        df_weekly.groupby(["week", "week_start", "exercise"], as_index=False)
        .agg({
            "Relative Volume": "sum",
            "Heavy Volume": "sum",
            "Hard Sets": "sum",
        })
        .sort_values("week_start")
    )

    # --- Show summary table ---
    st.dataframe(df_weekly_summary, use_container_width=True, hide_index=True, height=480)

    # --- Select exercise for visualization ---
    exercises_available = sorted(df_weekly_summary["exercise"].unique())
    selected_exercise_weekly = st.selectbox("Select exercise for weekly volume histogram", exercises_available)

    # --- Filter data for selected exercise and last 16 weeks ---
    df_plot_weekly = df_weekly_summary[df_weekly_summary["exercise"] == selected_exercise_weekly].copy()
    df_plot_weekly = df_plot_weekly.sort_values("week_start")
    cutoff_date = datetime.now() - timedelta(weeks=16)
    df_plot_weekly = df_plot_weekly[df_plot_weekly["week_start"] >= cutoff_date]

    if not df_plot_weekly.empty:
        import plotly.graph_objects as go

        fig = go.Figure()

        # --- Add Relative Volume ---
        fig.add_trace(go.Bar(
            x=df_plot_weekly["week_start"],
            y=df_plot_weekly["Relative Volume"],
            name="Relative Volume",
            marker_color="#9bafd9",
            opacity=0.8,
            yaxis="y1"
        ))

        # --- Add Heavy Volume ---
        fig.add_trace(go.Bar(
            x=df_plot_weekly["week_start"],
            y=df_plot_weekly["Heavy Volume"],
            name="Heavy Volume",
            marker_color="#d9534f",
            opacity=0.8,
            yaxis="y2"
        ))

        # --- Add Hard Sets ---
        fig.add_trace(go.Bar(
            x=df_plot_weekly["week_start"],
            y=df_plot_weekly["Hard Sets"],
            name="Hard Sets",
            marker_color="#5cb85c",
            opacity=0.8,
            yaxis="y3"
        ))

     
        # )
        fig.update_layout(
            title=f"{selected_exercise_weekly} — Weekly Training Metrics (Last 4 Months)",
            barmode="group",

            # Shrink main plot horizontally so multiple right y-axes fit
            xaxis=dict(
                domain=[0.0, 0.82],
                title="Week Starting",
                tickformat="%b %d",
                showgrid=False
            ),

            # y1 (left)
            yaxis=dict(
                title=dict(text="Relative Volume", font=dict(color="#9bafd9")),
                tickfont=dict(color="#9bafd9"),
                anchor="x",
                overlaying=None
            ),

            # y2 (right, inner)
            yaxis2=dict(
                title=dict(text="Heavy Volume", font=dict(color="#d9534f")),
                tickfont=dict(color="#d9534f"),
                overlaying="y",
                side="right",
                anchor="x",
                position=0.82   # <= MAX allowed
            ),

            # y3 (right, outer)
            yaxis3=dict(
                title=dict(text="Hard Sets", font=dict(color="#5cb85c")),
                tickfont=dict(color="#5cb85c"),
                overlaying="y",
                side="right",
                anchor="x",
                position=0.90   # <= MAX allowed
            ),

            legend=dict(x=0.02, y=1.1, orientation="h"),
            bargap=0.15,
            margin=dict(l=60, r=120, t=60, b=40),
            template="plotly_white",
        )


        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No weekly data for the selected exercise in the last 4 months.")

else:
    st.info("No weekly data available yet.")

# ======================================================
# === EXERCISE HISTORY OVERVIEW ========================
# ======================================================

st.subheader("🏋️ Exercise History Overview")

all_exercises = sorted({
    ex.get("exercise_name", "")
    for w in raw_data
    for ex in w.get("exercises", [])
    if ex.get("exercise_name")
})
selected_history_ex = st.selectbox("Select an exercise to view history", all_exercises)

history_rows = []
for workout_day in raw_data:
    raw_date = workout_day.get("date") or ""
    formatted_date = format_date(raw_date) if raw_date else "—"
    for exercise in workout_day.get("exercises", []):
        if exercise.get("exercise_name") == selected_history_ex:
            history_rows.append({
                "raw_date": raw_date,
                "date": formatted_date,
                "Relative Volume": exercise.get("volume_relative", 0),
                "Heavy Volume": exercise.get("heavy_sets", 0),
                "Hard Sets": exercise.get("hard_sets", 0),
            })

if history_rows:
    df_history = pd.DataFrame(history_rows).sort_values("raw_date", ascending=False).drop(columns=["raw_date"])
   
    st.dataframe(df_history, use_container_width=True, hide_index=True, height=480)
else:
    st.info("No records found for this exercise.")


# ======================================================
# === PLOTLY VOLUME TREND (MOBILE SAFE) ================
# ======================================================

if history_rows:
    import plotly.graph_objects as go
    df_plot = pd.DataFrame(history_rows).copy()
    df_plot["raw_date"] = pd.to_datetime(df_plot["date"], errors="coerce")
    df_plot = df_plot.dropna(subset=["raw_date"]).sort_values("raw_date")
    cutoff_date = datetime.now() - timedelta(days=180)
    df_plot = df_plot[df_plot["raw_date"] >= cutoff_date]

    if not df_plot.empty:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_plot["raw_date"], y=df_plot["Relative Volume"], name="Relative Volume", marker_color="#9bafd9", opacity=0.8))
        fig.add_trace(go.Scatter(x=df_plot["raw_date"], y=df_plot["Heavy Volume"], mode="lines+markers", name="Heavy Volume",
                                 line=dict(color="#d9534f", width=3), marker=dict(size=8), yaxis="y2"))
        fig.update_layout(
            title=f"{selected_history_ex} — Volume Trends (Last 6 Months)",
            xaxis=dict(title="Date", tickformat="%b-%d", showgrid=False),
            yaxis=dict(title=dict(text="Relative Volume", font=dict(color="#3e64ad")), tickfont=dict(color="#3e64ad")),
            yaxis2=dict(title=dict(text="Heavy Volume", font=dict(color="#d9534f")), tickfont=dict(color="#d9534f"), overlaying="y", side="right"),
            bargap=0.2,
            legend=dict(x=0.02, y=1.1, orientation="h"),
            margin=dict(l=50, r=50, t=80, b=50),
            template="plotly_white",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.write("v.a4")

        df["date_dt"] = pd.to_datetime(df["date"], format="%b-%d", errors="coerce")
        cutoff_date = datetime.now() - timedelta(days=120)
        df_recent = df[df["date_dt"] >= cutoff_date].copy()

        df_exercise_counts_4m = (
            df_recent.groupby("exercise")
            .size()
            .reset_index(name="entries_last_4m")
            .sort_values("entries_last_4m", ascending=False)
        )

        st.subheader("📈 Exercise Frequency (Last 4 Months)")
        st.dataframe(df_exercise_counts_4m, use_container_width=True, hide_index=True)
        st.session_state["exercise_counts_4m"] = df_exercise_counts_4m

        st.markdown(
            """
            <style>
            .scroll-container {overflow-x: auto; padding-left: 10px; padding-right: 10px;}
            .scroll-container::-webkit-scrollbar {height: 8px;}
            .scroll-container::-webkit-scrollbar-thumb {background-color: #bbb; border-radius: 4px;}
            </style>
            """,
            unsafe_allow_html=True
        )
        st.markdown('<div class="scroll-container">', unsafe_allow_html=True)
        st.dataframe(df, use_container_width=False, height=320, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

st.markdown("""<div style="height: 200px;"></div>""", unsafe_allow_html=True)

