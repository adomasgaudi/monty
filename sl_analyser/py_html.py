# strengthlevel_report.py
import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd
import requests

# --- Optional name->username mapping ---------------------------
try:
    # If you have variables.py or SL_analyser/variables.py with NAME_TO_USERNAME, we'll use it.
    from SL_analyser.variables import NAME_TO_USERNAME  # type: ignore
except Exception:
    try:
        from variables import NAME_TO_USERNAME  # type: ignore
    except Exception:
        NAME_TO_USERNAME = {}  # fallback; pass --username explicitly

USER_AGENT = "Mozilla/5.0"
WORKOUTS_PAGE_TEMPLATE = "https://my.strengthlevel.com/{username}/workouts"
WORKOUTS_API_URL = "https://my.strengthlevel.com/api/workouts"
PREFILL_REGEX = re.compile(r"window\.prefill\s*=\s*(\[[\s\S]*?\]);")

# ---------------- Core fetching helpers ----------------
def fetch_page(url: str) -> str:
    r = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    return r.text

def parse_prefill_for_user_id(html_text: str) -> str:
    m = PREFILL_REGEX.search(html_text)
    if not m:
        raise ValueError("prefill JSON not found in workouts page")
    try:
        prefill = json.loads(m.group(1))
    except Exception as exc:
        raise ValueError("failed to parse prefill JSON") from exc

    for blob in prefill:
        req = blob.get("request", {})
        if req.get("url") == "/api/workouts":
            uid = req.get("params", {}).get("user_id")
            if uid:
                return uid
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
    r = requests.get(WORKOUTS_API_URL, params=params,
                     headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.json()

def flatten_workouts(payload: dict) -> list[dict]:
    rows: list[dict] = []
    for w in payload.get("data", []):
        date = w.get("date")
        for ex in (w.get("exercises") or []):
            name = ex.get("exercise_name", "")
            sets = ex.get("sets") or []
            if not sets:
                rows.append({"date": date, "exercise": name,
                             "weight": "", "reps": "", "notes": ""})
            else:
                for s in sets:
                    rows.append({
                        "date": date,
                        "exercise": name,
                        "weight": s.get("weight", ""),
                        "reps": s.get("reps", ""),
                        "notes": s.get("notes", ""),
                    })
    return rows

# ---------------- HTML report ----------------
def make_html(df: pd.DataFrame, username: str) -> str:
    # Format date (MMM-dd) and ensure string for grouping
    if "date" in df.columns:
        _parsed = pd.to_datetime(df["date"], errors="coerce")
        df = df.copy()
        df["date"] = _parsed.dt.strftime("%b-%d").fillna(df["date"].astype(str))

    # Build a row style function that alternates color by date group
    # Factorize date to 0/1/0/1...
    groups = pd.factorize(df["date"].astype(str))[0] % 2

    def row_style(row: pd.Series):
        i = row.name
        # two soft backgrounds; text stays dark
        if groups[i] == 0:
            return ["background-color: #f2f4f7; color: #111;"] * len(row)
        else:
            return ["background-color: #fbfbfc; color: #111;"] * len(row)

    styler = (
        df.style
          .apply(row_style, axis=1)
          .set_properties(**{"border": "1px solid #e5e7eb", "padding": "6px"})
          .hide(axis="index")
    )

    table_html = styler.to_html()  # self-contained table + CSS

    # Wrap in a minimal HTML document
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>StrengthLevel DATA — @{username}</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
  body {{
    font: 14px system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    color: #111; background: #fff; padding: 24px;
  }}
  h1 {{ font-size: 20px; margin: 0 0 12px; }}
  .muted {{ color: #667085; margin-bottom: 18px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ background: #eef2f6; text-align: left; padding: 8px; border: 1px solid #e5e7eb; }}
</style>
</head>
<body>
  <h1>StrengthLevel DATA — @{username}</h1>
  <div class="muted">Rows: {len(df)}</div>
  {table_html}
</body>
</html>"""
    return doc

# ---------------- CLI ----------------
def resolve_username(name: str | None, username: str | None) -> str:
    if username:
        return username
    if name:
        if NAME_TO_USERNAME:
            u = NAME_TO_USERNAME.get(name)
            if not u:
                raise SystemExit(f"--name '{name}' not found in NAME_TO_USERNAME")
            return u
        raise SystemExit("--name provided but NAME_TO_USERNAME mapping is empty. Use --username instead.")
    raise SystemExit("Provide --username or --name")

def main():
    ap = argparse.ArgumentParser(description="Generate an HTML report of StrengthLevel workouts.")
    ap.add_argument("--name", help="Mapped display name (looked up in variables.NAME_TO_USERNAME)")
    ap.add_argument("--username", help="StrengthLevel username (overrides --name)")
    ap.add_argument("--out", default="report.html", help="Output HTML path (default: report.html)")
    args = ap.parse_args()

    username = resolve_username(args.name, args.username)

    try:
        html = fetch_page(WORKOUTS_PAGE_TEMPLATE.format(username=username))
        user_id = parse_prefill_for_user_id(html)
        payload = fetch_workouts_payload(user_id)
        rows = flatten_workouts(payload)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    if not rows:
        print("No data found.")
        sys.exit(0)

    df = pd.DataFrame(rows, columns=["date", "exercise", "weight", "reps", "notes"])

    html_doc = make_html(df, username=username)
    out_path = Path(args.out)
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {out_path.resolve()}")

if __name__ == "__main__":
    main()
