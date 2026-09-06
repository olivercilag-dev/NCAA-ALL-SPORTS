import hashlib
from datetime import datetime, timezone

SPORTS_ALLOWED={"Football","Soccer","Basketball","Volleyball","Baseball","Softball","Ice Hockey","Field Hockey","Track & Field","Swimming & Diving"}

def normalize(raw, source):
    sport=raw.get("sport")
    if sport=="Tennis": return None
    if sport not in SPORTS_ALLOWED: return None
    home=str(raw.get("home","")).strip(); away=str(raw.get("away","")).strip()
    start=str(raw.get("start_utc","")).strip()
    if not home or not away or not start: return None
    key=f"{sport}|{home.lower()}|{away.lower()}|{start[:10]}"
    eid=hashlib.sha256(key.encode()).hexdigest()[:24]
    return {
      "id":eid,"sport":sport,"gender":raw.get("gender",""),
      "competition":raw.get("competition","NCAA"),
      "home":home,"away":away,"start_utc":start,
      "status":raw.get("status","Scheduled"),"venue":raw.get("venue",""),
      "source":source
    }
