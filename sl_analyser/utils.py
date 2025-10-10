import requests
import json
import re

def fetch_user_id(username: str, headers: dict, base_url: str) -> str:
    """Extract user_id from a user's StrengthLevel workouts page."""
    
    session = requests.Session()
    session.headers.update(headers)
    
    html = session.get(f"{base_url}/{username}/workouts").text
    match = re.search(r"window\.prefill\s*=\s*(\[[\s\S]*?\]);", html)
    
    if not match:
        raise ValueError("Could not find prefill JSON — page structure may have changed.")
    
    prefill = json.loads(match.group(1))
    return prefill[0]["request"]["params"]["user_id"]
