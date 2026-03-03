import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from utils import fetch_user_id, fetch_raw_workouts
from variables import NAME_TO_USERNAME, EXERCISE_DATA


BASE_URL = "https://my.strengthlevel.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}


# ------------------------------------------------------
# HELPERS
# ------------------------------------------------------
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


# ------------------------------------------------------
# ENRICHMENT
# ------------------------------------------------------
def enrich_workouts_with_bodyweight_load(raw_data):
    """Attach bodyweight contribution and equipment weight to each exercise."""

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

    for workout in raw_data:
        bw = get_bodyweight(workout)
        for exercise in workout.get("exercises", []):
            bwp, eq_w = get_exercise_load_params(exercise.get("exercise_name", ""))
            bw_load, internal = compute_loads(bw, bwp, eq_w)

            exercise["bodyweight_p"] = bwp
            exercise["bodyweight_load"] = bw_load
            exercise["equipment_weight"] = eq_w
            exercise["internal_load"] = internal

    return raw_data


def enrich_workouts_with_1rm(raw_data):
    """Compute per-set and per-exercise 1RM using modified Epley3 formula."""

    def compute_set_1rm(weight, reps, internal_load):
        if weight > 0 and reps > 0:
            return epley3_record(weight, reps, internal_load)
        return None

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
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

    return raw_data


def enrich_workouts_with_rir(raw_data):
    """Estimate Reps in Reserve (RIR) for each set based on exercise 1RM."""

    def compute_rir(weight, reps, one_rm, internal_load):
        if weight > 0 and reps > 0 and one_rm is not None:
            max_reps = epley3_reps(weight, one_rm, internal_load)
            if max_reps is None:
                return None, None
            rir = round(max_reps - reps, 2)
            return rir, max_reps
        return None, None

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            one_rm = exercise.get("one_rep_max")
            internal = float(exercise.get("internal_load") or 0.0)
            if one_rm is None:
                continue

            for s in exercise.get("sets", []):
                w = float(s.get("weight") or 0.0)
                r = int(s.get("reps") or 0)
                rir, max_reps = compute_rir(w, r, one_rm, internal)
                s["RIR"] = rir
                s["max_reps"] = max_reps

    return raw_data


def enrich_workouts_with_hard_sets(raw_data):
    """Add count of 'hard sets' to each exercise (reps > 2 and RIR < 7)."""

    def is_hard_set(reps, rir):
        return (reps is not None and rir is not None and reps > 2 and rir < 7)

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            count = 0
            for s in exercise.get("sets", []):
                reps = s.get("reps")
                rir = s.get("RIR")
                if is_hard_set(reps, rir):
                    count += 1
            exercise["hard_sets"] = count

    return raw_data


def enrich_workouts_with_volume(raw_data):
    """Compute per-exercise training volume."""

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

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            vol_raw, vol_rel = compute_volumes(exercise)
            exercise["volume_raw"] = vol_raw
            exercise["volume_relative"] = vol_rel

    return raw_data


def enrich_workouts_with_heavy_volume(raw_data):
    """Compute heavy volume (85% & 93%) adjusted for internal load."""

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

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            one_rm = float(exercise.get("one_rep_max") or 0.0)
            internal = float(exercise.get("internal_load") or 0.0)

            if one_rm <= 0:
                exercise["heavy_sets"] = 0
                continue

            t85, t93 = calc_thresholds(one_rm, internal)
            score = 0

            for s in exercise.get("sets", []):
                w = float(s.get("weight") or 0.0)
                r = int(s.get("reps") or 0)
                score += score_set(w, r, t85, t93)

            exercise["heavy_sets"] = round(score / 3, 1)

    return raw_data


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
                rows.append(
                    {
                        "date": format_date(workout_day["date"]),
                        "exercise": ex.get("exercise_name"),
                        "weight": s.get("weight"),
                        "Reps": s.get("reps"),
                        "1RM": ex.get("one_rep_max"),
                    }
                )
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
# MOBILE STYLING
# ------------------------------------------------------
st.write("v.b0.7b")
st.markdown(
    """
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
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------
# UI SETUP
# ------------------------------------------------------
selected_name = st.selectbox("Select person", list(NAME_TO_USERNAME.keys()), key="person_select")
raw_data = get_data_from_username(selected_name)

st.title("StrengthLevel DATA")

df = create_workout_df(raw_data)
if df.empty:
    st.warning("No data returned.")
    st.stop()


# ------------------------------------------------------
# SINGLE EXERCISE VIEW
# ------------------------------------------------------
exercise_counts = df["exercise"].value_counts().reset_index()
exercise_counts.columns = ["exercise", "count"]

selected_exercise_single = st.selectbox(
    "Choose an exercise",
    exercise_counts["exercise"],
    key="exercise_single",
)

st.subheader("Training Sets")
df_selected = df[df["exercise"] == selected_exercise_single]
st.dataframe(
    df_selected.drop(columns=["exercise"], errors="ignore"),
    use_container_width=True,
    hide_index=True,
    height=480,
)


# ------------------------------------------------------
# WEEKLY SUMMARY (week shown as date range)
# ------------------------------------------------------
st.header("📊 Weekly Volume Summary")

weekly_rows = []
for w in raw_data:
    raw_date = w.get("date")
    if not raw_date:
        continue

    d = datetime.strptime(raw_date, "%Y-%m-%d")

    iso_year, iso_week, _ = d.isocalendar()
    week_start = datetime.fromisocalendar(iso_year, iso_week, 1)  # Mon
    week_end = datetime.fromisocalendar(iso_year, iso_week, 7)    # Sun

    week_label = f"{week_start.strftime('%Y-%m-%d')} → {week_end.strftime('%Y-%m-%d')}"

    for ex in w.get("exercises", []):
        weekly_rows.append(
            {
                "week_start": week_start,  # for correct sorting/filtering
                "week": week_label,        # for display
                "exercise": ex.get("exercise_name", ""),
                "Relative Volume": ex.get("volume_relative", 0),
                "Heavy Volume": ex.get("heavy_sets", 0),
                "Hard Sets": ex.get("hard_sets", 0),
            }
        )

df_weekly = pd.DataFrame(weekly_rows)

df_weekly_summary = (
    df_weekly.groupby(["week_start", "week", "exercise"], as_index=False)
    .agg({"Relative Volume": "sum", "Heavy Volume": "sum", "Hard Sets": "sum"})
    .sort_values("week_start", ascending=False)
)

st.dataframe(
    df_weekly_summary.drop(columns=["week_start"]),
    use_container_width=True,
    hide_index=True,
    height=480,
)


# ------------------------------------------------------
# WEEKLY CHARTS (3 separate bar charts)
# ------------------------------------------------------
st.subheader("📈 Weekly Metrics Charts (Separate)")

exercises_available = sorted(df_weekly_summary["exercise"].unique())
selected_ex_hist = st.selectbox(
    "Select exercise for weekly charts",
    exercises_available,
    key="weekly_charts_ex",
)

df_plot = df_weekly_summary[df_weekly_summary["exercise"] == selected_ex_hist].copy()

df_plot["plot_date"] = df_plot["week_start"] + timedelta(days=1)  # small spacing
cutoff = datetime.now() - timedelta(weeks=16)
df_plot = df_plot[df_plot["plot_date"] >= cutoff].sort_values("plot_date")

if df_plot.empty:
    st.info("No weekly data available for this exercise.")
else:
    import plotly.graph_objects as go

    def bar_chart(title, y_col):
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=df_plot["week"],  # shows "YYYY-MM-DD → YYYY-MM-DD"
                y=df_plot[y_col],
                name=y_col,
                opacity=0.85,
            )
        )
        fig.update_layout(
            title=title,
            xaxis=dict(title="Week (Mon → Sun)", type="category", showgrid=False),
            yaxis=dict(title=y_col),
            margin=dict(l=60, r=30, t=60, b=90),
            template="plotly_white",
        )
        return fig

    st.plotly_chart(
        bar_chart(f"{selected_ex_hist} — Relative Volume (Last 4 Months)", "Relative Volume"),
        use_container_width=True,
    )
    st.plotly_chart(
        bar_chart(f"{selected_ex_hist} — Heavy Volume (Last 4 Months)", "Heavy Volume"),
        use_container_width=True,
    )
    st.plotly_chart(
        bar_chart(f"{selected_ex_hist} — Hard Sets (Last 4 Months)", "Hard Sets"),
        use_container_width=True,
    )


# ------------------------------------------------------
# EXERCISE HISTORY (with zero-days)
# ------------------------------------------------------
st.header("🏋️ Exercise History Overview")

all_exercises = sorted(
    {
        ex.get("exercise_name", "")
        for w in raw_data
        for ex in w.get("exercises", [])
        if ex.get("exercise_name")
    }
)

selected_history = st.selectbox("Exercise history:", all_exercises, key="history_exercise")

history_rows = []
for w in raw_data:
    raw_date = w["date"]
    formatted = format_date(raw_date)

    todays = [ex for ex in w.get("exercises", []) if ex.get("exercise_name") == selected_history]

    if todays:
        ex = todays[0]
        history_rows.append(
            {
                "raw_date": raw_date,
                "date": formatted,
                "Relative Volume": ex.get("volume_relative", 0),
                "Heavy Volume": ex.get("heavy_sets", 0),
                "Hard Sets": ex.get("hard_sets", 0),
            }
        )
    else:
        history_rows.append(
            {
                "raw_date": raw_date,
                "date": formatted,
                "Relative Volume": 0,
                "Heavy Volume": 0,
                "Hard Sets": 0,
            }
        )

df_history = (
    pd.DataFrame(history_rows)
    .sort_values("raw_date", ascending=False)
    .drop(columns=["raw_date"])
)

st.dataframe(df_history, use_container_width=True, hide_index=True, height=480)


# ------------------------------------------------------
# QUICK TABLE: ALL SETS OF SELECTED EXERCISE
# ------------------------------------------------------
exercise_dict = dict(zip(exercise_counts["exercise"], exercise_counts["count"]))

selected_exercise_table = st.selectbox(
    "Choose an exercise (table)",
    list(exercise_dict.keys()),
    key="exercise_table",
)

df_selected_exercise = df[df["exercise"] == selected_exercise_table].reset_index(drop=True)

st.write("table 1")
st.dataframe(
    df_selected_exercise.drop(columns=["exercise"], errors="ignore"),
    use_container_width=True,
    hide_index=True,
    height=480,
)
