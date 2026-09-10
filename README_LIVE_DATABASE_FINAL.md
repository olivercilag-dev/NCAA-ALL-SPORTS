# NCAA ALL SPORTS — LIVE DATA ENGINE

This build uses public NCAA scoreboard JSON endpoints on `data.ncaa.com` without an API key. The server fetches data server-side (avoiding browser CORS), merges valid events, and refreshes the local cache every 15 minutes while the Render instance is awake.

## Important fix in this build
The NCAA endpoint uses a date path of `YYYY/MM/DD`. The previous build incorrectly sent the whole ISO date as one path segment, which caused the live fetch to return no events and left the bundled snapshot in place.

## Refresh behavior
- `REFRESH_MINUTES=15`
- `LOOKAHEAD_DAYS=7` (today + next 7 days)
- Parallel upstream requests for faster refresh
- Last good cache is retained if an upstream source is unavailable
- `/api/health` shows current source/status
- `/api/refresh` triggers an on-demand refresh
- `/api/events` serves the current cache
- Tennis is excluded by project requirement

## Render
Start Command:

```text
python server.py
```

Environment:

```text
REFRESH_MINUTES=15
LOOKAHEAD_DAYS=7
```

A free Render instance may sleep. Refreshing every 15 minutes is reliable while the instance is awake; after a restart, the refresh thread starts again. The free filesystem should not be treated as permanent historical storage.
