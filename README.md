# NCAA ALL SPORTS — ULTIMATE FINAL

Professional NCAA schedule interface with a server-side live-data cache. The browser loads `/api/events`; it no longer depends on a huge hard-coded JavaScript event list.

## Live data engine

The server is configured to query the public NCAA scoreboard JSON domain (`data.ncaa.com`) without an API key or paid sports-data subscription. It normalizes the returned contests into the format used by the UI and refreshes the cache every 15 minutes.

- **Primary source:** NCAA public scoreboard JSON
- **Refresh:** every 15 minutes
- **Coverage window:** today + next 7 days
- **Server-side fetching:** avoids browser CORS problems
- **Failure protection:** the last good `data.json` cache is retained if an upstream response is empty/unavailable
- **Manual refresh:** `GET /api/refresh`
- **Health:** `GET /api/health`
- **Tennis:** intentionally excluded
- **Baseball:** included

## Render

Start command:

```text
python server.py
```

The included `render.yaml` sets `REFRESH_MINUTES=15` and `LOOKAHEAD_DAYS=7`.

### Free Render limitation

A free Render web service can sleep while inactive and its local filesystem is not permanent storage. This build therefore refreshes every 15 minutes while the instance is awake and also attempts a refresh on the first API request when the local cache is stale. Permanent historical storage across instance replacement would require persistent/external storage later.

## Legal/data-use guardrail

This build does not bypass login, CAPTCHA, paywalls, anti-bot systems, or access controls. It only requests the public NCAA JSON endpoint. Public accessibility alone is not a blanket redistribution license, so the final public deployment should continue to follow the NCAA site's current terms, rate limits, attribution requirements, and any applicable redistribution rules.
