import requests
import re
import json
from rich.console import Console
from rich.pretty import Pretty

console = Console()

# ---------------------------------------
# Constants
# ---------------------------------------
USER_AGENT = "Mozilla/5.0"
URL_WORKOUTS = "https://my.strengthlevel.com/{username}/workouts"
API_MY_WORKOUTS = "https://my.strengthlevel.com/api/workouts"
PREFILL_REGEX = re.compile(r"window\.prefill\s*=\s*(\[[\s\S]*?\]);")

# ---------------------------------------
# Fetch HTML
# ---------------------------------------
def fetch_page(url: str) -> str:
    response = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text

# ---------------------------------------
# Extract user_id from embedded JSON
# ---------------------------------------
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

# ---------------------------------------
# Fetch workouts JSON using user_id
# ---------------------------------------
def fetch_workouts_payload(user_id: str, limit: int = 20) -> dict:
    params = {
        "user_id": user_id,
        "workout.fields": "date,exercises",
        "workoutexercise.fields": "exercise_name,sets",
        "set.fields": "weight,reps,notes",
        "limit": limit,
        "offset": 0,
    }
    response = requests.get(API_MY_WORKOUTS, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    return response.json()

# ---------------------------------------
# Flatten to rows
# ---------------------------------------
def flatten_workouts(payload: dict) -> list[dict]:
    rows = []
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

# ---------------------------------------
# Main
# ---------------------------------------
def fetch_first_n_workouts(username: str, n: int = 20):
    console.log(f"Fetching first {n} workouts for [bold]{username}[/bold]...")
    html = fetch_page(URL_WORKOUTS.format(username=username))
    user_id = parse_prefill_for_user_id(html)
    console.log(f"User ID found: [cyan]{user_id}[/cyan]")

    payload = fetch_workouts_payload(user_id, limit=n)
    rows = flatten_workouts(payload)

    console.rule(f"[bold green]Showing first {n} workouts ({len(rows)} total sets)[/bold green]")
    console.print(Pretty(rows, expand_all=False))
    return rows


# ---------------------------------------
# Example run
# ---------------------------------------
if __name__ == "__main__":
    username = "adomasgaudi"  # change this to any username
    try:
        fetch_first_n_workouts(username, n=20)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
