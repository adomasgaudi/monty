# streamlit_app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin, urlencode
from datetime import datetime
import time

st.set_page_config(page_title="StrengthLevel → CSV", page_icon="🏋️", layout="centered")

st.title("🏋️ StrengthLevel workouts → CSV")
st.write(
    "Enter your **StrengthLevel username**. If your workouts are not public, paste your **session cookie** "
    "from your logged-in browser on `my.strengthlevel.com`."
)

with st.expander("How to get your session cookie (optional)"):
    st.markdown(
        """
1. Log into **https://my.strengthlevel.com** in your browser.
2. Open DevTools → **Application/Storage** → **Cookies** for `my.strengthlevel.com`.
3. Copy the cookie that represents your authenticated session (often something like `session`, `auth`, or similar).
4. Paste it below. **Do not share it with anyone.** You can clear it later by logging out of StrengthLevel.
        """
    )

username = st.text_input("StrengthLevel username", help="Example: john_doe")
session_cookie = st.text_input("Optional session cookie", type="password", help="Paste only if your workouts aren’t public.")
run_btn = st.button("Fetch workouts")

# --------------------------
# Utility helpers
# --------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StrengthLevelCSV/1.0; +https://strengthlevel.com/)",
    "Accept-Language": "en-US,en;q=0.9",
}

def clean_text(x):
    return " ".join((x or "").split())

def to_dt(s):
    """Try to parse a date/time string; return original if unknown."""
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%b %d, %Y", "%Y-%m-%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except Exception:
            pass
    return s

def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")

# --------------------------
# Strategy A: Attempt public profile scraping on strengthlevel.com
# --------------------------
def scrape_public_profile(username: str) -> pd.DataFrame:
    """
    Best-effort scraper for any public workout pages linked from a user profile on strengthlevel.com.
    Many accounts do not expose public workouts; this will then return an empty DataFrame.
    """
    base = "https://strengthlevel.com"
    profile_urls = [
        f"{base}/users/{username}",
        f"{base}/u/{username}",
        f"{base}/profile/{username}",
    ]
    workouts = []

    session = requests.Session()
    session.headers.update(HEADERS)

    for profile_url in profile_urls:
        try:
            r = session.get(profile_url, timeout=15)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")

            # Try to find obvious workout containers (best-effort, selectors may change)
            # Look for cards/rows that contain date + list of exercises and sets.
            candidates = soup.select(".workout, .workout-card, .workout-item, .log, .entry, article")
            for card in candidates:
                date_txt = clean_text(card.select_one(".date, time, .workout-date, .meta") .get_text(strip=True) if card.select_one(".date, time, .workout-date, .meta") else "")
                title = clean_text(card.select_one("h2, h3, .title") .get_text(strip=True) if card.select_one("h2, h3, .title") else "")
                # Extract exercise rows
                rows = card.select("tr, li, .set, .exercise-row")
                if not rows:
                    # Attempt paragraphs
                    rows = card.select("p")
                for row in rows:
                    txt = clean_text(row.get_text(" ", strip=True))
                    # Heuristics: split on common patterns "Exercise – sets x reps @ weight"
                    if len(txt) < 3:
                        continue
                    workouts.append(
                        {
                            "source": profile_url,
                            "date": date_txt,
                            "session_title": title,
                            "entry": txt,
                        }
                    )

            # Also check if there is a pagination to a 'workouts' listing
            link_candidates = [a.get("href") for a in soup.select("a[href]")]
            for href in link_candidates:
                if not href:
                    continue
                if any(k in href.lower() for k in ["workout", "log", "training"]):
                    workouts.extend(scrape_simple_list(urljoin(profile_url, href), session))
        except requests.RequestException:
            continue

    return pd.DataFrame(workouts)

def scrape_simple_list(list_url: str, session: requests.Session) -> list:
    """
    Crawl a listing page that likely contains workouts; follow basic pagination if present.
    """
    results = []
    visited = set()
    next_url = list_url

    for _ in range(10):  # limit pagination to avoid runaway
        if not next_url or next_url in visited:
            break
        visited.add(next_url)
        r = session.get(next_url, timeout=15)
        if r.status_code != 200:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select(".workout, .workout-card, .workout-item, .log, article")
        for card in cards:
            date_txt = clean_text(card.select_one(".date, time, .workout-date, .meta").get_text(strip=True) if card.select_one(".date, time, .workout-date, .meta") else "")
            title = clean_text(card.select_one("h2, h3, .title").get_text(strip=True) if card.select_one("h2, h3, .title") else "")
            rows = card.select("tr, li, .set, .exercise-row, p")
            for row in rows:
                txt = clean_text(row.get_text(" ", strip=True))
                if len(txt) < 3:
                    continue
                results.append({"source": next_url, "date": date_txt, "session_title": title, "entry": txt})

        # find a 'next' link
        next_link = soup.find("a", string=lambda s: s and "next" in s.lower())
        next_url = urljoin(next_url, next_link.get("href")) if next_link and next_link.get("href") else None
        time.sleep(0.5)  # be polite

    return results

# --------------------------
# Strategy B: Authenticated fetch on my.strengthlevel.com via cookie
# (User supplies *their own* cookie; we do NOT automate login)
# --------------------------
def fetch_authenticated_workouts(session_cookie_value: str) -> pd.DataFrame:
    """
    Best-effort: try a few likely JSON endpoints used by the web app.
    This does NOT bypass authentication; it only works if the user provides a valid cookie.
    Endpoint paths may change; we handle failures gracefully.
    """
    base = "https://my.strengthlevel.com"
    s = requests.Session()
    s.headers.update(HEADERS)
    # Attach user-provided cookie key *name* is unknown; we attach as 'session' and also raw header for flexibility.
    s.cookies.set("session", session_cookie_value, domain="my.strengthlevel.com", secure=True, httponly=False)
    s.headers["Cookie"] = f"session={session_cookie_value}"

    candidates = [
        "/api/workouts?limit=200",
        "/api/v1/workouts?limit=200",
        "/api/workouts",  # fallback
    ]
    records = []

    for path in candidates:
        url = urljoin(base, path)
        try:
            r = s.get(url, timeout=20)
            if r.status_code != 200:
                continue
            data = r.json()
            # Expect either {"workouts":[...]} or a list
            items = data.get("workouts", data if isinstance(data, list) else [])
            for w in items:
                # Try common fields; keep extra keys as a flattened string
                date_val = w.get("date") or w.get("performed_at") or w.get("created_at")
                title = w.get("title") or w.get("name") or ""
                notes = w.get("notes") or ""
                # exercises/sets often nested
                exercises = w.get("exercises") or w.get("items") or []
                if isinstance(exercises, list) and exercises:
                    for ex in exercises:
                        ex_name = ex.get("name") or ex.get("exercise") or ""
                        sets = ex.get("sets") or ex.get("entries") or []
                        if isinstance(sets, list) and sets:
                            for sset in sets:
                                reps = sset.get("reps") or sset.get("repetitions")
                                weight = sset.get("weight") or sset.get("kg") or sset.get("lb")
                                rir = sset.get("rir")
                                rpe = sset.get("rpe")
                                records.append(
                                    {
                                        "date": date_val,
                                        "session_title": title,
                                        "exercise": ex_name,
                                        "reps": reps,
                                        "weight": weight,
                                        "rpe": rpe,
                                        "rir": rir,
                                        "notes": notes,
                                    }
                                )
                        else:
                            # No per-set detail
                            records.append(
                                {
                                    "date": date_val,
                                    "session_title": title,
                                    "exercise": ex_name,
                                    "reps": None,
                                    "weight": None,
                                    "rpe": None,
                                    "rir": None,
                                    "notes": notes,
                                }
                            )
                else:
                    # No exercises key; store raw
                    records.append(
                        {
                            "date": date_val,
                            "session_title": title,
                            "exercise": "",
                            "reps": None,
                            "weight": None,
                            "rpe": None,
                            "rir": None,
                            "notes": notes,
                        }
                    )
            if records:
                break
        except requests.RequestException:
            continue
        except ValueError:
            # not JSON
            continue

    return pd.DataFrame.from_records(records)

# --------------------------
# Run
# --------------------------
if run_btn:
    if not username.strip():
        st.error("Please enter a username.")
        st.stop()

    with st.spinner("Looking for public workouts…"):
        df_public = scrape_public_profile(username.strip())

    if not df_public.empty:
        # Normalize public entries into structured columns when possible
        df_public["parsed_date"] = df_public["date"].apply(to_dt)
        ordered_cols = ["parsed_date", "date", "session_title", "entry", "source"]
        df_public = df_public[ordered_cols]
        st.success(f"Found {len(df_public)} workout entries from public pages (best effort).")
        st.dataframe(df_public.head(50))
        st.download_button(
            "Download CSV (public best-effort)",
            data=df_to_csv_bytes(df_public.rename(columns={"parsed_date": "date_parsed"})),
            file_name=f"{username}_strengthlevel_public_workouts.csv",
            mime="text/csv",
        )
    else:
        st.info("No public workout entries found for that username.")

    if session_cookie.strip():
        with st.spinner("Fetching authenticated workouts with your cookie…"):
            df_auth = fetch_authenticated_workouts(session_cookie.strip())

        if df_auth.empty:
            st.warning(
                "Could not fetch authenticated workouts. Your cookie may be invalid, expired, or endpoints have changed."
            )
        else:
            # Tidy up types
            for col in ["reps", "weight", "rpe", "rir"]:
                if col in df_auth.columns:
                    df_auth[col] = pd.to_numeric(df_auth[col], errors="ignore")
            # Attempt to parse date
            if "date" in df_auth.columns:
                try:
                    df_auth["date_parsed"] = pd.to_datetime(df_auth["date"], errors="coerce")
                except Exception:
                    pass

            st.success(f"Fetched {len(df_auth)} rows from authenticated endpoints.")
            st.dataframe(df_auth.head(50))
            st.download_button(
                "Download CSV (authenticated)",
                data=df_to_csv_bytes(df_auth),
                file_name=f"{username}_strengthlevel_workouts.csv",
                mime="text/csv",
            )

    if df_public.empty and not session_cookie.strip():
        st.stop()
        # User will see the prior info messages
