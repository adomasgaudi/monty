# streamlit_app.py
import streamlit as st
import requests, re, json, time
import pandas as pd

st.set_page_config(page_title="StrengthLevel → CSV (clean)", layout="centered")
st.title("StrengthLevel → all workouts (public)")

NAME_TO_USERNAME = {
    "Adomas": "adomasgaudi",
    "Sandra": "sandrakri",
    "Pocius": "jpociuss",
    "Johanness": "johannesschut",
    "dzuljeta": "dzuljeta",
    "mantas": "mantasp",
    "kristina": "andromeda94",
    "andrius": "andriusp",
}

names = list(NAME_TO_USERNAME.keys())
default_index = names.index("dzuljeta") if "dzuljeta" in names else 0
selected_name = st.selectbox("Select person", names, index=default_index)
username = NAME_TO_USERNAME[selected_name]

max_workouts = st.number_input("Max workouts to fetch (0 = all)", value=0, min_value=0, step=1)

if st.button("Fetch workouts"):
    base_page = f"https://my.strengthlevel.com/{username}/workouts"
    st.write(f"GET {base_page}")

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

    prefill = json.loads(m.group(1))
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

    api = "https://my.strengthlevel.com/api/workouts"
    headers = {"User-Agent": "Mozilla/5.0"}
    rows, limit, offset = [], 200, 0
    fetched, total_expected = 0, None

    st.write("Fetching from public API:", api)
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
        total_expected = total_expected or meta.get("count")

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
        if max_workouts and fetched >= max_workouts:
            break
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

    # ---- DROP unwanted columns ----
    drop_cols = set()
    # explicitly named:
    for c in ["name", "username", "i", "id", "workout_id"]:
        if c in df.columns:
            drop_cols.add(c)
    # any *_id columns just in case:
    for c in df.columns:
        if c.endswith("_id"):
            drop_cols.add(c)

    df = df.drop(columns=list(drop_cols), errors="ignore")

        # Reorder to a clean, friendly schema
    preferred = ["date", "bodyweight", "exercise", "weight", "reps", "notes", "dropset", "percentile"]
    ordered = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    df = df[ordered]

    # >>> NEW: format date as MMM-dd
    if "date" in df.columns:
        _parsed = pd.to_datetime(df["date"], errors="coerce")
        df["date"] = _parsed.dt.strftime("%b-%d").fillna(df["date"])

    st.success(f"Parsed {len(df)} rows across {fetched} workouts for {selected_name} (@{username}).")
    st.dataframe(df.head(50))

    st.download_button(
        "Download CSV (clean)",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{username}_strengthlevel_workouts_clean.csv",
        mime="text/csv",
    )
