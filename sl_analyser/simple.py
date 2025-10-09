import json
import re
import requests
import pandas as pd
import streamlit as st

# ---------------------------------------
# Imports and constants (logic-only)
# ---------------------------------------
try:
    # When running from project root and treating folder as a package
    from SL_analyser.variables import NAME_TO_USERNAME  # type: ignore
except Exception:
    try:
        # When running the script inside the same folder
        from variables import NAME_TO_USERNAME  # type: ignore
    except Exception:
        NAME_TO_USERNAME = {}

USER_AGENT = "Mozilla/5.0"
WORKOUTS_PAGE_TEMPLATE = "https://my.strengthlevel.com/{username}/workouts"
WORKOUTS_API_URL = "https://my.strengthlevel.com/api/workouts"
PREFILL_REGEX = re.compile(r"window\.prefill\s*=\s*(\[[\s\S]*?\]);")


def fetch_page(url: str) -> str:
    response = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text


def parse_prefill_for_user_id(html_text: str) -> str:
    match = PREFILL_REGEX.search(html_text)
    if not match:
        raise ValueError("prefill JSON not found in page")

    try:
        prefill = json.loads(match.group(1))
    except Exception as exc:
        raise ValueError("failed to parse prefill JSON") from exc

    for blob in prefill:
        request_info = blob.get("request", {})
        if request_info.get("url") == "/api/workouts":
            user_id = request_info.get("params", {}).get("user_id")
            if user_id:
                return user_id

    raise ValueError("user_id not found in prefill JSON")


def fetch_workouts_payload(user_id: str) -> dict:
    params = {
        "user_id": user_id,
        "workout.fields": "date,exercises",
        "workoutexercise.fields": "exercise_name,sets",
        "set.fields": "weight,reps,notes",
        "limit": 1000,
        "offset": 0,
    }
    response = requests.get(WORKOUTS_API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    return response.json()


def flatten_workouts(payload: dict) -> list[dict]:
    rows: list[dict] = []
    for workout in payload.get("data", []):
        date = workout.get("date")
        for exercise in (workout.get("exercises") or []):
            exercise_name = exercise.get("exercise_name", "")
            for set_item in (exercise.get("sets") or []):
                rows.append({
                    "date": date,
                    "exercise": exercise_name,
                    "weight": set_item.get("weight"),
                    "reps": set_item.get("reps"),
                    "notes": set_item.get("notes"),
                })
    return rows


def build_dataframe(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ---------------------------------------
# UI (Streamlit-only)
# ---------------------------------------
st.set_page_config(page_title="StrengthLevel DATA")
st.title("StrengthLevel DATA (minimal)")

names = list(NAME_TO_USERNAME.keys())
if not names:
    st.error("No names available. Check variables module import.")
    st.stop()

selected_index = names.index("dzuljeta") if "dzuljeta" in names else 0
selected_name = st.selectbox("Select person", names, index=selected_index)
username = NAME_TO_USERNAME[selected_name]

try:
    base_page_html = fetch_page(WORKOUTS_PAGE_TEMPLATE.format(username=username))
    user_id = parse_prefill_for_user_id(base_page_html)
    payload = fetch_workouts_payload(user_id)
    rows = flatten_workouts(payload)
except requests.RequestException as exc:
    st.error(f"Network error: {exc}")
    st.stop()
except ValueError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:
    st.error(f"Unexpected error: {exc}")
    st.stop()

if not rows:
    st.info("No workouts found.")
else:
    df = build_dataframe(rows)
    st.dataframe(df, use_container_width=True)

