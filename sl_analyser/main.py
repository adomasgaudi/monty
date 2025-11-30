import streamlit as st
import pandas as pd
from utils import fetch_user_id, fetch_raw_workouts
from variables import NAME_TO_USERNAME, EXERCISE_DATA
from datetime import datetime, timedelta

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

BASE_URL = "https://my.strengthlevel.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}


# ======================================================
# === HELPERS ==========================================
# ======================================================

def format_date(d: str) -> str:
    return datetime.strptime(d, "%Y-%m-%d").strftime("%b-%d")

def epley3_reps(w: float, w_rec: float, w_i: float) -> float:
    """Estimate reps given weight, 1RM, and internal load."""
    if w is None or w_rec is None or w_i is None:
        return None
    denom = 3.33 * (w + w_i)
    if denom == 0:
        return None
    try:
        reps = (100 * (w_rec + w_i)) / denom - 29
        return round(reps, 2)
    except Exception:
        return None

def epley3_record(w: float, reps: float, w_i: float) -> float:
    """Estimate 1RM given working weight, reps, and internal load."""
    if w is None or reps is None or w_i is None:
        return None
    try:
        return round((3.33 * (w + w_i) * (reps + 29)) / 100 - w_i, 2)
    except ZeroDivisionError:
        return None

def epley3_weight(w_rec: float, reps: float, w_i: float) -> float:
    """Estimate working weight given 1RM, target reps, and internal load."""
    if w_rec is None or reps is None or w_i is None:
        return None
    try:
        return round((100 * (w_rec + w_i)) / (3.33 * (reps + 29)) - w_i, 2)
    except ZeroDivisionError:
        return None


# ======================================================
# === DATA ENRICHMENT ==================================
# ======================================================


def enrich_workouts_with_bodyweight_load(raw_data):
    """Attach bodyweight contribution and equipment weight to each exercise."""

    # --- local helpers (fully collapsible inside outer function) -----

    def get_bodyweight(workout):
        return float(workout.get("bodyweight") or 0.0)

    def get_exercise_load_params(ex_name):
        name = (ex_name or "").strip()
        data = EXERCISE_DATA.get(name, {})
        bwp = float(data.get("bwp") or 0.0)
        eq_w = float(data.get("eq_w") or 0.0)
        return bwp, eq_w

    def compute_loads(bodyweight, bwp, eq_w):
        bw_load = round(bodyweight * bwp, 2)
        internal = round(bw_load + eq_w, 2)
        return bw_load, internal

    

    # --- main logic --------------------------------------------------

    for workout in raw_data:
        bw = get_bodyweight(workout)
        for exercise in workout.get("exercises", []):
            def attach_fields(exercise, bodyweight):
                bwp, eq_w = get_exercise_load_params(exercise.get("exercise_name", ""))
                bw_load, internal = compute_loads(bodyweight, bwp, eq_w)

                exercise["bodyweight_p"] = bwp
                exercise["bodyweight_load"] = bw_load
                exercise["equipment_weight"] = eq_w
                exercise["internal_load"] = internal
            attach_fields(exercise, bw)

    return raw_data

def enrich_workouts_with_1rm(raw_data):
    """Compute per-set and per-exercise 1RM using modified Epley3 formula."""

    def compute_set_1rm(weight, reps, internal_load):
        if weight > 0 and reps > 0:
            return epley3_record(weight, reps, internal_load)
        return None

    # --- main logic ------------------------------------------------

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            def process_exercise(exercise):
                internal_load = float(exercise.get("internal_load") or 0.0)
                set_1rms = []

                for s in exercise.get("sets", []):
                    w = float(s.get("weight") or 0.0)
                    r = int(s.get("reps") or 0)

                    one_rm = compute_set_1rm(w, r, internal_load)
                    s["one_rep_max"] = one_rm
                    if one_rm is not None:
                        set_1rms.append(one_rm)

                exercise["one_rep_max"] = max(set_1rms) if set_1rms else None
            process_exercise(exercise)

    return raw_data
def enrich_workouts_with_rir(raw_data):
    """Estimate Reps in Reserve (RIR) for each set based on exercise 1RM."""

    # --- helpers -----------------------------------------------------

    def compute_rir(weight, reps, one_rm, internal_load):
        if weight > 0 and reps > 0 and one_rm is not None:
            max_reps = epley3_reps(weight, one_rm, internal_load)
            if max_reps is None:
                return None, None
            rir = round(max_reps - reps, 2)
            return rir, max_reps
        return None, None

    def process_exercise(exercise):
        one_rm = exercise.get("one_rep_max")
        internal = float(exercise.get("internal_load") or 0.0)
        if one_rm is None:
            return
        for s in exercise.get("sets", []):
            w = float(s.get("weight") or 0.0)
            r = int(s.get("reps") or 0)
            rir, max_reps = compute_rir(w, r, one_rm, internal)
            s["RIR"] = rir
            s["max_reps"] = max_reps

    # --- main logic --------------------------------------------------

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            process_exercise(exercise)

    return raw_data
def enrich_workouts_with_hard_sets(raw_data):
    """Add count of 'hard sets' to each exercise (reps > 3 and RIR < 3)."""

    # --- helpers -----------------------------------------------------

    def is_hard_set(reps, rir):
        return (reps is not None and rir is not None
                and reps > 3 and rir < 3)

    def process_exercise(exercise):
        count = 0
        for s in exercise.get("sets", []):
            reps = s.get("reps")
            rir = s.get("RIR")
            if is_hard_set(reps, rir):
                count += 1
        exercise["hard_sets"] = count

    # --- main logic --------------------------------------------------

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            process_exercise(exercise)

    return raw_data
def enrich_workouts_with_volume(raw_data):
    """Compute per-exercise training volume."""

    # --- helpers -----------------------------------------------------

    def compute_volumes(exercise):
        one_rm = float(exercise.get("one_rep_max") or 0.0)
        total = 0.0
        relative = 0.0

        for s in exercise.get("sets", []):
            w = float(s.get("weight") or 0.0)
            r = int(s.get("reps") or 0)
            total += w * r
            if one_rm > 0:
                relative += (w * r) / (one_rm * 0.8)

        return round(total, 0), round(relative, 0)

    def process_exercise(exercise):
        vol_raw, vol_rel = compute_volumes(exercise)
        exercise["volume_raw"] = vol_raw
        exercise["volume_relative"] = vol_rel

    # --- main logic --------------------------------------------------

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            process_exercise(exercise)

    return raw_data
def enrich_workouts_with_heavy_volume(raw_data):
    """Compute heavy volume (85% & 93%) adjusted for internal load."""

    # --- helpers -----------------------------------------------------

    def calc_thresholds(one_rm, internal_load):
        t85 = (0.85 * (one_rm + internal_load)) - internal_load
        t93 = (0.93 * (one_rm + internal_load)) - internal_load
        return t85, t93

    def score_set(weight, reps, t85, t93):
        if weight > t93:
            return 2 * reps
        if weight > t85:
            return reps
        return 0

    def process_exercise(exercise):
        one_rm = float(exercise.get("one_rep_max") or 0.0)
        internal = float(exercise.get("internal_load") or 0.0)

        if one_rm <= 0:
            exercise["volume_heavy"] = 0
            return

        t85, t93 = calc_thresholds(one_rm, internal)
        score = 0

        for s in exercise.get("sets", []):
            w = float(s.get("weight") or 0.0)
            r = int(s.get("reps") or 0)
            score += score_set(w, r, t85, t93)

        exercise["volume_heavy"] = round(score / 3, 1)

    # --- main logic --------------------------------------------------

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            process_exercise(exercise)

    return raw_data

# def enrich_workouts_with_rir(raw_data):
#     """Estimate Reps in Reserve (RIR) for each set based on exercise 1RM."""
#     for workout in raw_data:
#         for exercise in workout.get("exercises", []):
#             one_rm = exercise.get("one_rep_max")
#             w_i = exercise.get("internal_load", 0.0)
#             if one_rm is None:
#                 continue
#             for s in exercise.get("sets", []):
#                 w = s.get("weight") or 0
#                 r = s.get("reps") or 0
#                 if w > 0 and r > 0:
#                     max_reps = epley3_reps(w, one_rm, w_i)
#                     if max_reps is not None:
#                         rir = round(max_reps - r, 2)
#                         s["RIR"] = rir
#                         s["max_reps"] = max_reps
#                 else:
#                     s["RIR"] = None
#                     s["max_reps"] = None
#     return raw_data

# def enrich_workouts_with_hard_sets(raw_data):
#     """Add count of 'hard sets' to each exercise (reps > 3 and RIR < 3)."""
#     for workout in raw_data:
#         for exercise in workout.get("exercises", []):
#             hard_count = 0
#             for s in exercise.get("sets", []):
#                 reps = s.get("reps")
#                 rir = s.get("RIR")
#                 if reps is not None and rir is not None:
#                     if reps > 3 and rir < 3:
#                         hard_count += 1
#             exercise["hard_sets"] = hard_count
#     return raw_data

# def enrich_workouts_with_volume(raw_data):
#     """Compute per-exercise training volume for each workout."""
#     for workout in raw_data:
#         for exercise in workout.get("exercises", []):
#             one_rm = exercise.get("one_rep_max") or 0
#             total_volume = 0
#             relative_volume = 0
#             for s in exercise.get("sets", []):
#                 w = s.get("weight") or 0
#                 r = s.get("reps") or 0
#                 total_volume += w * r
#                 if one_rm > 0:
#                     relative_volume += (w * r) / (one_rm * 0.8)
#             exercise["volume_raw"] = round(total_volume, 0)
#             exercise["volume_relative"] = round(relative_volume, 0)
#     return raw_data

# def enrich_workouts_with_heavy_volume(raw_data):
#     """Compute heavy volume (85% & 93% thresholds) adjusted for internal load."""
#     for workout in raw_data:
#         for exercise in workout.get("exercises", []):
#             one_rm = exercise.get("one_rep_max") or 0
#             w_i = exercise.get("internal_load", 0.0)
#             if one_rm <= 0:
#                 exercise["volume_heavy"] = 0
#                 continue
#             t85_external = (0.85 * (one_rm + w_i)) - w_i
#             t93_external = (0.93 * (one_rm + w_i)) - w_i
#             heavy_points = 0
#             for s in exercise.get("sets", []):
#                 w = s.get("weight") or 0
#                 r = s.get("reps") or 0
#                 if w > t93_external:
#                     heavy_points += 2 * r
#                 elif w > t85_external:
#                     heavy_points += r
#             exercise["volume_heavy"] = round(heavy_points/3,1)
#     return raw_data


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
with st.expander(f"📋 Sets for {selected_exercise}", expanded=False):
    st.dataframe(df_selected_exercise.drop(columns=["exercise"], errors="ignore"),
                 use_container_width=True, height=480, hide_index=True)



# ======================================================
# === DAILY VOLUME SUMMARY =============================
# ======================================================

summary_rows = []
for i, workout_day in enumerate(raw_data):
    date_str = format_date(workout_day["date"])
    day_rows = []
    for exercise in workout_day.get("exercises", []):
        day_rows.append({
            "date": date_str,
            "exercise": exercise.get("exercise_name", ""),
            "Relative Volume": exercise.get("volume_relative", 0),
            "Heavy Volume": exercise.get("volume_heavy", 0),
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
            "Heavy Volume": exercise.get("volume_heavy", 0),
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

        # --- Configure layout with 3 vertical axes ---
        fig.update_layout(
            title=f"{selected_exercise_weekly} — Weekly Training Metrics (Last 4 Months)",
            barmode="group",
            xaxis=dict(
                title="Week Starting",
                tickformat="%b %d",
                showgrid=False
            ),
            yaxis=dict(  # y1
                title="Relative Volume",
                titlefont=dict(color="#9bafd9"),
                tickfont=dict(color="#9bafd9")
            ),
            yaxis2=dict(  # y2
                title="Heavy Volume",
                titlefont=dict(color="#d9534f"),
                tickfont=dict(color="#d9534f"),
                anchor="free",
                overlaying="y",
                side="right",
                position=1.0
            ),
            yaxis3=dict(  # y3
                title="Hard Sets",
                titlefont=dict(color="#5cb85c"),
                tickfont=dict(color="#5cb85c"),
                anchor="free",
                overlaying="y",
                side="right",
                position=1.08  # slightly further right
            ),
            legend=dict(x=0.02, y=1.1, orientation="h"),
            bargap=0.15,
            margin=dict(l=60, r=90, t=60, b=40),
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
                "Heavy Volume": exercise.get("volume_heavy", 0),
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

