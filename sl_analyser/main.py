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
    if w is None or w_rec is None or w_i is None:
        return None

    denom = 3.33 * (w + w_i)
    if denom == 0:  # prevent divide-by-zero crash
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
    # st.write(raw_data)
    return raw_data

def enrich_workouts_with_rir(raw_data):
    """Estimate Reps in Reserve (RIR) for each set based on exercise 1RM."""
    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            one_rm = exercise.get("one_rep_max")
            w_i = exercise.get("internal_load", 0.0)

            if one_rm is None:
                continue

            for s in exercise.get("sets", []):
                w = s.get("weight")
                r = s.get("reps")
                if w is not None and r is not None:
                    max_reps = epley3_reps(w, one_rm, w_i)
                    # st.write(max_reps)
                    if max_reps is not None:
                        rir = round(max_reps - r, 2)
                        s["RIR"] = rir
                        s["max_reps"] = max_reps
    return raw_data

def enrich_workouts_with_volume(raw_data):
    """Compute per-exercise training volume for each workout."""
    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            one_rm = exercise.get("one_rep_max")
            total_volume = 0
            relative_volume = 0

            for s in exercise.get("sets", []):
                w = s.get("weight") or 0
                r = s.get("reps") or 0
                total_volume += w * r

                if one_rm and one_rm > 0:
                    relative_volume += (w * r) / (one_rm * 0.8)

            exercise["volume_raw"] = round(total_volume, 2)
            exercise["volume_relative"] = round(relative_volume, 3)
    return raw_data

def enrich_workouts_with_heavy_volume(raw_data):
    """Compute heavy volume (85% & 93% thresholds) adjusted for internal load."""
    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            one_rm = exercise.get("one_rep_max")
            w_i = exercise.get("internal_load", 0.0)

            if not one_rm or one_rm <= 0:
                exercise["volume_heavy"] = 0
                continue

            # Compute threshold external weights
            t85_external = (0.85 * (one_rm + w_i)) - w_i
            t93_external = (0.93 * (one_rm + w_i)) - w_i

            heavy_points = 0
            for s in exercise.get("sets", []):
                w = s.get("weight") or 0
                r = s.get("reps") or 0

                if w > t93_external:
                    heavy_points += 2 * r
                elif w > t85_external:
                    heavy_points += r

            exercise["volume_heavy"] = heavy_points
    return raw_data

    """Compute 'heavy volume' based on 85% and 93% of daily 1RM."""
    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            one_rm = exercise.get("one_rep_max")
            if not one_rm or one_rm <= 0:
                exercise["volume_heavy"] = 0
                continue

            heavy_points = 0
            for s in exercise.get("sets", []):
                w = s.get("weight") or 0
                r = s.get("reps") or 0

                if w > 0.93 * one_rm:
                    heavy_points += 2 * r
                elif w > 0.85 * one_rm:
                    heavy_points += r

            exercise["volume_heavy"] = heavy_points
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
    enriched = enrich_workouts_with_rir(enriched)
    enriched = enrich_workouts_with_volume(enriched)
    enriched = enrich_workouts_with_heavy_volume(enriched)  # 👈 NEW STEP
    # st.write(enriched)
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


with st.expander("📋 Full Workout Data", expanded=False):
    with st.spinner(f"Fetching and rendering {selected_name}'s data..."):
        
        df = create_workout_df(raw_data)
        st.dataframe(df, use_container_width=True, height=640, hide_index=True)

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




with st.expander("📊 Daily Exercise Volume Summary", expanded=False):
    with st.spinner("Calculating daily training volume summary..."):

        # Prepare rows for the summary table
        summary_rows = []

        for workout_day in raw_data:
            date_str = format_date(workout_day["date"])
            for exercise in workout_day.get("exercises", []):
                summary_rows.append({
                    "date": date_str,
                    "exercise": exercise.get("exercise_name", ""),
                    "Relative Volume": exercise.get("volume_relative", 0),
                    "Heavy Volume": exercise.get("volume_heavy", 0),
                })

        if summary_rows:
            df_summary = pd.DataFrame(summary_rows)
            st.dataframe(
                df_summary,
                use_container_width=True,
                hide_index=True,
                height=480
            )
        else:
            st.info("No volume data available yet.")
            
            
            
          # ======================================================
# === ALL-TIME EXERCISE HISTORY ========================
# ======================================================

st.subheader("🏋️ Exercise History Overview")

# --- Collect all unique exercises
all_exercises = sorted({
    ex.get("exercise_name", "")
    for w in raw_data
    for ex in w.get("exercises", [])
    if ex.get("exercise_name")
})

# --- Let user pick an exercise
selected_history_ex = st.selectbox("Select an exercise to view history", all_exercises)

# --- Build history table
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
            })

# --- Display results
if history_rows:
    df_history = pd.DataFrame(history_rows)

    # Sort by true chronological date (descending)
    df_history = df_history.sort_values("raw_date", ascending=False).drop(columns=["raw_date"])

    with st.expander(f"📅 Workouts for {selected_history_ex}", expanded=True):
        st.dataframe(df_history, use_container_width=True, hide_index=True, height=480)
else:
    st.info("No records found for this exercise.")

# ======================================================
# === EXERCISE VOLUME TREND GRAPH (Plotly Mobile Safe) ==
# ======================================================

if not history_rows:
    st.info("No data available for plotting.")
else:
    import plotly.graph_objects as go
    from datetime import datetime, timedelta

    # Prepare data
    df_plot = pd.DataFrame(history_rows).copy()
    df_plot["raw_date"] = pd.to_datetime(df_plot["raw_date"], errors="coerce")
    df_plot = df_plot.dropna(subset=["raw_date"]).sort_values("raw_date")

    # Filter for the last 6 months
    cutoff_date = datetime.now() - timedelta(days=180)
    df_plot = df_plot[df_plot["raw_date"] >= cutoff_date]

    if df_plot.empty:
        st.info("No data available for the last 6 months.")
    else:
        # Create interactive Plotly figure
        fig = go.Figure()

        # Relative Volume (bars)
        fig.add_trace(
            go.Bar(
                x=df_plot["raw_date"],
                y=df_plot["Relative Volume"],
                name="Relative Volume",
                marker_color="#9bafd9",
                opacity=0.8,
            )
        )

        # Heavy Volume (line)
        fig.add_trace(
            go.Scatter(
                x=df_plot["raw_date"],
                y=df_plot["Heavy Volume"],
                mode="lines+markers",
                name="Heavy Volume",
                line=dict(color="#d9534f", width=3),
                marker=dict(size=8),
                yaxis="y2",
            )
        )

        # Dual y-axes layout
        fig.update_layout(
            title=f"{selected_history_ex} — Volume Trends (Last 6 Months)",
            xaxis=dict(
                title="Date",
                tickformat="%b-%d",
                showgrid=False,
            ),
            yaxis=dict(
                title="Relative Volume",
                titlefont=dict(color="#3e64ad"),
                tickfont=dict(color="#3e64ad"),
            ),
            yaxis2=dict(
                title="Heavy Volume",
                titlefont=dict(color="#d9534f"),
                tickfont=dict(color="#d9534f"),
                overlaying="y",
                side="right",
            ),
            bargap=0.2,
            legend=dict(x=0.02, y=1.1, orientation="h"),
            margin=dict(l=50, r=50, t=80, b=50),
            template="plotly_white",
        )

        # Show in Streamlit (mobile safe)
        st.plotly_chart(fig, use_container_width=True)
