# NCAA ALL SPORTS — LIVE DATA ENGINE

## Data source
The server uses the public JSON scoreboard endpoints on `data.ncaa.com`, the NCAA data domain, without an API key or paid data subscription.

- Refresh interval: **15 minutes** (`REFRESH_MINUTES=15`)
- Lookahead: **today + next 7 days** (`LOOKAHEAD_DAYS=7`)
- Server-side fetch: avoids browser CORS issues
- Cache: `data.json` is replaced atomically only when valid events are returned
- If an upstream endpoint is unavailable, the last good cache is kept instead of blanking the site
- `/api/health` reports refresh status and event count
- `/api/refresh` starts an on-demand refresh
- Tennis is excluded by project requirement

## Important free-hosting note
On a free Render web service, the instance can sleep when inactive. While the instance is awake the background worker refreshes every 15 minutes; after a sleep/restart, the first `/api/events` request attempts a refresh when the cache is stale. Render's free filesystem is not permanent storage, so long-term persistence across instance replacement requires persistent storage later.

## Render
Start command:

```text
python server.py
```

Environment variables already supported:

```text
REFRESH_MINUTES=15
LOOKAHEAD_DAYS=7
```
