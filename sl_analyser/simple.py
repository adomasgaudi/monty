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
URL_WORKOUTS = "https://my.strengthlevel.com/{username}/workouts"
API_MY_WORKOUTS = "https://my.strengthlevel.com/api/workouts"
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
    response = requests.get(API_MY_WORKOUTS, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
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


def get_names_for_ui() -> list[str]:
    names_list = list(NAME_TO_USERNAME.keys())
    return names_list if names_list else ["— no names —"]


def get_default_index(names: list[str], preferred: str) -> int:
    return names.index(preferred) if preferred in names else 0


def resolve_username(selected_name: str | None) -> str | None:
    if not selected_name or selected_name == "— no names —":
        return None
    return NAME_TO_USERNAME.get(selected_name)


def safe_fetch_rows(username: str) -> tuple[list[dict], str | None]:
    try:
        base_page_html = fetch_page(URL_WORKOUTS.format(username=username))
        user_id = parse_prefill_for_user_id(base_page_html)
        payload = fetch_workouts_payload(user_id)
        rows = flatten_workouts(payload)
        return rows, None
    except requests.RequestException as exc:
        return [], f"Network error: {exc}"
    except ValueError as exc:
        return [], str(exc)
    except Exception as exc:
        return [], f"Unexpected error: {exc}"

def fetch_rows_for_selected_name(selected_name: str) -> list[dict]:
    username = resolve_username(selected_name)
    if not username:
        st.error("No names available. Check variables module import.")
        st.stop()
    rows, error_message = safe_fetch_rows(username)
    if error_message:
        st.error(error_message)
        st.stop()
    return rows

def workouts_table(rows, *, title: str | None = None, transform=None) -> pd.DataFrame | None:
    """
    Handles empty-state, builds a DataFrame, applies an optional transform, and renders the table.
    Returns the rendered DataFrame (or None if nothing to show).
    """
    if title:
        st.subheader(title)

    if not rows:
        st.info("No workouts found.")
        return None

    df = build_dataframe(rows)
    if callable(transform):
        try:
            df = transform(df)
        except Exception as e:
            st.warning(f"Transform failed: {e}")

    st.dataframe(df, use_container_width=True)
    

names = get_names_for_ui()

def select_and_fetch() -> list[dict]:
    """Select person and return their workout data."""
    selected_name = st.selectbox("Select person", names, index=get_default_index(names, "dzuljeta"))
    return fetch_rows_for_selected_name(selected_name)

# ---------------------------------------
# UI (Streamlit-only)
# ---------------------------------------
st.set_page_config(page_title="StrengthLevel DATA")
st.title("StrengthLevel DATA (minimal)")

rows = select_and_fetch()
workouts_table(rows, title="All workouts")


