# streamlit_app.py
import streamlit as st
import requests, re, json, time
import pandas as pd
import numpy as np
from variables import NAME_TO_USERNAME, BW_PCT_RAW

st.set_page_config(page_title="StrengthLevel DATA", layout="centered")
st.title("StrengthLevel DATA")


_BW_KEYMAP = {k.strip().lower(): v for k, v in BW_PCT_RAW.items()}
# st.write("_BW_KEYMAP:", _BW_KEYMAP)  # Streamlit-friendly "console.log"
def _norm(s: str) -> str:
    return (s or "").strip().lower()

# --- UI: choose person by NAME; we look up the username ---
names = list(NAME_TO_USERNAME.keys())
default_index = names.index("dzuljeta") if "dzuljeta" in names else 0
selected_name = st.selectbox("Select person", names, index=default_index)
username = NAME_TO_USERNAME[selected_name]

# Auto-fetch when selection changes (no button needed)
# Check if we should fetch (either first load or selection changed)
should_fetch = True

# Store the last selected person in session state to detect changes
if 'last_selected_person' not in st.session_state:
    st.session_state.last_selected_person = selected_name
elif st.session_state.last_selected_person != selected_name:
    st.session_state.last_selected_person = selected_name
    should_fetch = True
else:
    should_fetch = False

# Only fetch if we need to (first load or selection changed)
if should_fetch:
    base_page = f"https://my.strengthlevel.com/{username}/workouts"

    # Load workouts page to extract window.prefill → user_id
    try:
        r = requests.get(base_page, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
    except requests.RequestException as e:
        st.error(f"Failed to load workouts page: {e}")
        st.stop()

    m = re.search(r"window\.prefill\s*=\s*(\[[\s\S]*?\]);", r.text)
    if not m:
        st.error("Could not find window.prefill JSON; page structure changed?")
        st.stop()

    try:
        prefill = json.loads(m.group(1))
    except Exception:
        st.error("Failed to parse window.prefill JSON.")
        st.stop()

    user_id = None
    for blob in prefill:
        req = blob.get("request", {})
        if req.get("url") == "/api/workouts":
            params = req.get("params", {})
            user_id = params.get("user_id")
            if user_id:
                break

    if not user_id:
        st.error("Could not extract user_id from page JSON.")
        st.stop()

    # Pull workouts via public API (paginate)
    api = "https://my.strengthlevel.com/api/workouts"
    headers = {"User-Agent": "Mozilla/5.0"}
    rows = []
    limit = 200
    offset = 0
    fetched = 0
    total_expected = None

    progress = st.progress(0)

    while True:
        params = {
            "user_id": user_id,
            "workout.fields": "date,bodyweight,total,exercises,timezone,timezone_offset_mins",
            "workoutexercise.fields": "exercise_name,exercise_name_url,sets,total,is_custom_exercise",
            "set.fields": "weight,reps,notes,dropset,percentile",
            "limit": limit,
            "offset": offset,
        }
        try:
            resp = requests.get(api, params=params, headers=headers, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as e:
            st.error(f"API request failed at offset {offset}: {e}")
            break
        except ValueError:
            st.error(f"Non-JSON response at offset {offset}.")
            break

        data = payload.get("data", [])
        meta = payload.get("meta", {})
        if total_expected is None:
            total_expected = meta.get("count")

        if not data:
            break

        for w in data:
            w_id = w.get("id")
            date = w.get("date")
            bodyweight = w.get("bodyweight")
            exs = w.get("exercises") or []

            if not exs:
                rows.append(
                    {
                        "workout_id": w_id,  # will be dropped later
                        "date": date,
                        "bodyweight": bodyweight,
                        "exercise": "",
                        "weight": None,
                        "reps": None,
                        "notes": "",
                        "dropset": False,
                        "percentile": None,
                    }
                )
                continue

            for ex in exs:
                ex_name = ex.get("exercise_name", "")
                sets = ex.get("sets") or []
                if sets:
                    for s in sets:
                        rows.append(
                            {
                                "workout_id": w_id,  # will be dropped later
                                "date": date,
                                "bodyweight": bodyweight,
                                "exercise": ex_name,
                                "weight": s.get("weight"),
                                "reps": s.get("reps"),
                                "notes": s.get("notes"),
                                "dropset": s.get("dropset", False),
                                "percentile": s.get("percentile"),
                            }
                        )
                else:
                    rows.append(
                        {
                            "workout_id": w_id,  # will be dropped later
                            "date": date,
                            "bodyweight": bodyweight,
                            "exercise": ex_name,
                            "weight": None,
                            "reps": None,
                            "notes": "",
                            "dropset": False,
                            "percentile": None,
                        }
                    )

        fetched += len(data)
        offset += limit

        if total_expected:
            progress.progress(min(1.0, fetched / float(total_expected)))
        time.sleep(0.15)
        if len(data) < limit:
            break

    if not rows:
        st.warning("No rows parsed.")
        st.stop()

    df = pd.DataFrame(rows)

    # numeric cleanup
    for col in ["weight", "reps", "percentile", "bodyweight"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="ignore")

    # Add body-weight percentage per exercise (case-insensitive)
    df["bw_pct"] = df["exercise"].map(lambda x: _BW_KEYMAP.get(_norm(x)))

    # --- internal weight & 1RM (Epley3) ---
    # internal weight = bodyweight * bw_pct
    df["internal_weight"] = df["bodyweight"] * df["bw_pct"]

    # Epley3 (from R_{epley3}(x) = 100(w_REC+w_i) / [3.33(x+w_i)] - 29)
    # => 1RM (w_REC) = ((R + 29) * 3.33 * (x + w_i)) / 100 - w_i
    def est_1rm_epley3(reps, wi, x):
        if pd.isna(reps) or reps <= 0:
            return np.nan
        if pd.isna(wi):
            return np.nan
        if pd.isna(x):
            x = 0.0
        try:
            r = float(reps)
            wi = float(wi)
            x = float(x)
            return ((r + 29.0) * 3.33 * (x + wi)) / 100.0 - wi
        except Exception:
            return np.nan

    df["est_1RM"] = df.apply(
        lambda row: est_1rm_epley3(row.get("reps"), row.get("internal_weight"), row.get("weight")),
        axis=1,
    ).round(1)

    # Drop unwanted columns: name, username, i, id, and any *_id (incl. workout_id)
    drop_cols = set()
    for c in ["name", "username", "i", "id", "workout_id"]:
        if c in df.columns:
            drop_cols.add(c)
    for c in df.columns:
        if c.endswith("_id"):
            drop_cols.add(c)
    df = df.drop(columns=list(drop_cols), errors="ignore")

    # Reorder to a clean schema
    preferred = [
        "date", "bodyweight", "bw_pct", "internal_weight",
        "exercise", "weight", "reps", "est_1RM",
        "notes", "dropset", "percentile",
    ]
    df = df[[c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]]

    # Format date as MMM-dd (e.g., Oct-02)
    if "date" in df.columns:
        _parsed = pd.to_datetime(df["date"], errors="coerce")
        df["date"] = _parsed.dt.strftime("%b-%d").fillna(df["date"])

    st.success(f"Parsed {len(df)} rows across {fetched} workouts for {selected_name} (@{username}).")

    # Hide selected columns in the on-screen table (keep them in CSV) and hide index
    hidden_cols = ["date", "bodyweight", "internal_weight", "percentile"]
    display_df = df.drop(columns=hidden_cols, errors="ignore")

    st.dataframe(display_df, use_container_width=True, height=640, hide_index=True)
    st.caption(f"Total rows: {len(df)}")

    st.download_button(
        "Download CSV (clean + bw% + est_1RM)",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{username}_strengthlevel_workouts_clean_1rm.csv",
        mime="text/csv",
    )

# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
