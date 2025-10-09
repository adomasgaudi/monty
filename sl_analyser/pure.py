# strengthlevel_minimal.py
import argparse
import json
import re
import sys
from typing import Dict, List, Tuple, Optional

import requests
import pandas as pd
import numpy as np

# ----------------------------
# Config / Constants
# ----------------------------
USER_AGENT = "Mozilla/5.0"
WORKOUTS_PAGE_TEMPLATE = "https://my.strengthlevel.com/{username}/workouts"
WORKOUTS_API_URL = "https://my.strengthlevel.com/api/workouts"
PREFILL_REGEX = re.compile(r"window\.prefill\s*=\s*(\[[\s\S]*?\]);")

# Optional: fill in your map (or pass username via CLI)
NAME_TO_USERNAME: Dict[str, str] = {
    "Adomas": "adomasgaudi",
    "Sandra": "sandrakri",
    "Pocius": "jpociuss",
    "Johanness": "johannesschut",
    "dzuljeta": "dzuljeta",
    "mantas": "mantasp",
    "kristina": "andromeda94",
    "andrius": "andriusp",
}

# Body-weight % lifted per exercise (expand/modify as needed)
BW_PCT_RAW: Dict[str, Optional[float]] = {
    "Back Extension": 0.4,
    "Balance lunges twist": 0.6,
    "Balance squat": 0.6,
    "Bench Press": 0.0,
    "Cable Overhead Tricep Extension": 0.0,
    "Chest Press": 0.0,
    "Deadlift": 0.2,
    "Decline Sit Up": 0.3,
    "Dips": 1.0,
    "Dumbbell Bench Press": 0.0,
    "Dumbbell Curl": 0.0,
    "Dumbbell Finger Curl": 0.0,
    "Dumbbell Lunge": 0.6,
    "Dumbbell Shoulder Press": 0.0,
    "Goblet Squat": 0.6,
    "Hack Squat": 0.6,
    "Hammer Curl": 0.0,
    "Hanging Knee Raise": None,
    "Hip Thrust": 0.4,
    "Incline Bench Press": 0.0,
    "Incline Chest Press": 0.0,
    "Incline Dumbbell Bench Press": 0.0,
    "Kettlebell Deadlift": 0.2,
    "Kettlebell High Pull": None,
    "Kettlebell Swing": None,
    "Leg Curl": 0.05,
    "Leg Extension": 0.05,
    "Leg Press": 0.05,
    "Lower Back Extension": 0.3,
    "Lunge": 0.6,
    "Lying Leg Raise": 0.2,
    "Lying Leg Curl": 0.05,
    "Lying leg curl single leg": 0.05,
    "Standing Leg Curl": 0.05,
    "Machine Lateral Raise": None,
    "Machine Calf Raise": 1,
    "Military Press": 0.0,
    "Neutral grip lat pulldown": 0.0,
    "Oblique Side Bends": 0.3,
    "Overhead Press": 0.0,
    "Pallof Press": None,
    "Pec fly oblique": None,
    "Plank": 1.0,
    "Plank one leg": 1.0,
    "Preacher Curl": 0.0,
    "Pull Ups": 1.0,
    "Push Ups": 1.0,
    "Reverse Grip Lat Pulldown": 0.0,
    "Roman Chair Side Bend": 0.3,
    "Romanian Deadlift": 0.2,
    "STRETCH (tempinai virvute i prieki)": None,
    "STRETCH - Virvute": None,
    "Side Plank": 1.0,
    "Single Dumbbell Cossack Squat": 0.6,
    "Single Leg Press": 0.05,
    "Single leg back extension": 0.4,
    "Sit Up": 0.3,
    "Skull Crusher": 0.0,
    "Sled Leg Press": 0.1,
    "Smith Machine Single Leg Deadlift": 0.2,
    "Smith Machine Incline Close Grip Push Up": 1,
    "Smith Machine Squat": 0.6,
    "Squat": 0.6,
    "Tricep Pushdown": 0.0,
    "Nordic Hamstring Curl": None,
    "One Arm Dumbbell Preacher Curl": 0.0,
    "One Arm Incline Dumbbell Lateral Raise": 0.0,
    "One leg RDL": 0.2,
}

# Build a case-insensitive lookup
_BW_KEYMAP = {k.strip().lower(): v for k, v in BW_PCT_RAW.items()}


# ----------------------------
# Fetching (pure logic)
# ----------------------------
def fetch_page(url: str) -> str:
    res = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
    res.raise_for_status()
    return res.text


def parse_prefill_for_user_id(html_text: str) -> str:
    m = PREFILL_REGEX.search(html_text)
    if not m:
        raise ValueError("prefill JSON not found in page")

    try:
        prefill = json.loads(m.group(1))
    except Exception as exc:
        raise ValueError("failed to parse prefill JSON") from exc

    for blob in prefill:
        req = blob.get("request", {})
        if req.get("url") == "/api/workouts":
            params = req.get("params", {})
            user_id = params.get("user_id")
            if user_id:
                return user_id

    raise ValueError("user_id not found in prefill JSON")


def fetch_workouts_payload(user_id: str) -> dict:
    params = {
        "user_id": user_id,
        "workout.fields": "date,bodyweight,exercises",
        "workoutexercise.fields": "exercise_name,sets",
        "set.fields": "weight,reps,notes,rir",   # include RIR for “hard sets”
        "limit": 1000,
        "offset": 0,
    }
    res = requests.get(WORKOUTS_API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    res.raise_for_status()
    return res.json()


def flatten_workouts(payload: dict) -> List[dict]:
    rows: List[dict] = []
    for w in payload.get("data", []):
        date = w.get("date")
        bodyweight = w.get("bodyweight")
        for ex in (w.get("exercises") or []):
            ex_name = ex.get("exercise_name", "")
            for s in (ex.get("sets") or []):
                rows.append(
                    {
                        "date": date,
                        "bodyweight": bodyweight,
                        "exercise": ex_name,
                        "weight": s.get("weight"),
                        "reps": s.get("reps"),
                        "rir": s.get("rir"),
                        "notes": s.get("notes"),
                    }
                )
    return rows


def fetch_rows_for_username(username: str) -> List[dict]:
    """
    One-shot convenience: username -> rows
    """
    html = fetch_page(WORKOUTS_PAGE_TEMPLATE.format(username=username))
    user_id = parse_prefill_for_user_id(html)
    payload = fetch_workouts_payload(user_id)
    return flatten_workouts(payload)


# ----------------------------
# Data shaping / analysis
# ----------------------------
def _norm(s: str) -> str:
    return (s or "").strip().lower()


def to_dataframe(rows: List[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    # Ensure numeric where possible
    for col in ("weight", "reps", "rir", "bodyweight"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def add_bw_pct_and_1rm(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds:
      - bw_pct (body-weight percentage per exercise)
      - internal_weight = bodyweight * bw_pct
      - est_1RM using Epley3 inversion you specified:
        R_epley3(x) = 100*(w_REC + w_i) / (3.33*(x + w_i)) - 29
        => w_REC = ((R + 29) * 3.33 * (x + w_i)) / 100 - w_i
    """
    df = df.copy()

    # Map BW%
    df["bw_pct"] = df["exercise"].map(lambda x: _BW_KEYMAP.get(_norm(x)))

    # internal weight
    df["internal_weight"] = df["bodyweight"] * df["bw_pct"]

    def est_1rm_epley3(reps, wi, x):
        if pd.isna(reps) or reps <= 0 or pd.isna(wi):
            return np.nan
        if pd.isna(x):
            x = 0.0
        r = float(reps)
        wi = float(wi)
        x = float(x)
        return ((r + 29.0) * 3.33 * (x + wi)) / 100.0 - wi

    df["est_1RM"] = df.apply(
        lambda row: est_1rm_epley3(row.get("reps"), row.get("internal_weight"), row.get("weight")),
        axis=1,
    ).round(1)

    return df


def subset_single_exercise(df: pd.DataFrame, exercise_name: str) -> pd.DataFrame:
    """
    Case-insensitive filter by exercise display name.
    """
    mask = df["exercise"].str.lower() == exercise_name.strip().lower()
    return df.loc[mask].copy()


def summarize_hard_sets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Define a 'hard set' as RIR in [1, 2, 3].
    Returns a summary table grouped by date and exercise with counts and best est_1RM.
    """
    if "rir" not in df.columns:
        raise ValueError("RIR not present. Ensure set.fields included 'rir' in fetch.")

    hard = df[(df["rir"].notna()) & (df["rir"].between(1, 3))]
    if hard.empty:
        return pd.DataFrame(columns=["date", "exercise", "hard_sets", "best_est_1RM"])

    out = (
        hard.groupby(["date", "exercise"], as_index=False)
            .agg(hard_sets=("rir", "count"), best_est_1RM=("est_1RM", "max"))
            .sort_values(["date", "exercise"])
    )
    return out


# ----------------------------
# CLI / Demo
# ----------------------------
def main():
    parser = argparse.ArgumentParser(description="Fetch and analyze StrengthLevel workouts (pure Python).")
    parser.add_argument("--username", type=str, default="", help="StrengthLevel username (overrides --name).")
    parser.add_argument("--name", type=str, default="dzuljeta", help="Friendly name mapped in NAME_TO_USERNAME.")
    parser.add_argument("--exercise", type=str, default="Bench Press", help="Exercise name for subset demo.")
    parser.add_argument("--csv", type=str, default="", help="Optional path to save the full enriched CSV.")
    args = parser.parse_args()

    # Resolve username
    username = args.username or NAME_TO_USERNAME.get(args.name, "")
    if not username:
        print("Error: no username provided and name not found in map.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching workouts for @{username} …")
    rows = fetch_rows_for_username(username)
    if not rows:
        print("No rows found.")
        sys.exit(0)

    # Build base df
    df = to_dataframe(rows)
    # Add bw% + 1RM
    df_enriched = add_bw_pct_and_1rm(df)

    # Demonstrations:
    print("\n=== First 10 enriched rows ===")
    print(df_enriched.head(10).to_string(index=False))

    # Single-exercise table
    one_ex = subset_single_exercise(df_enriched, args.exercise)
    print(f"\n=== '{args.exercise}' rows (up to 10) ===")
    if one_ex.empty:
        print("(none)")
    else:
        print(one_ex.head(10).to_string(index=False))

    # Hard sets summary (RIR 1–3)
    try:
        hard_summary = summarize_hard_sets(df_enriched)
        print("\n=== Hard sets summary (RIR 1–3) ===")
        if hard_summary.empty:
            print("(none)")
        else:
            print(hard_summary.head(20).to_string(index=False))
    except ValueError as e:
        # RIR not present in the payload
        print(f"\n[Note] {e}")

    if args.csv:
        df_enriched.to_csv(args.csv, index=False)
        print(f"\nSaved enriched data to: {args.csv}")


if __name__ == "__main__":
    main()
