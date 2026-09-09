# NCAA ALL SPORTS — LIVE BUILD

A responsive NCAA multi-sport chronological feed for phone and PC.

## Included
- One chronological feed
- Yesterday / Today / Tomorrow / Next 7 Days
- UTC times
- Search and sport filter
- Event details
- Sport colors
- Baseball included
- Tennis excluded
- 11 languages with visible country flags
- Hebrew with RTL layout
- SQLite cache
- `/api/health`, `/api/events`, `/api/sources`
- Automatic background refresh

## Live data engine
The backend contains adapters for ESPN public scoreboard endpoints for sports where those endpoints return data. It also supports additional public/licensed JSON feeds through environment variables.

The application never invents events. If a feed is unavailable or does not cover a sport, that sport can remain empty.

Supported optional environment variables:
- NCAA_SCHEDULE_URL / NCAA_API_KEY
- OFFICIAL_SCHEDULE_URL / OFFICIAL_API_KEY
- REFRESH_MINUTES
- DATABASE_PATH

## Important
A technically accessible public endpoint is not automatically a license to redistribute its data. Before public commercial use, confirm the applicable provider terms and attribution/redistribution rights. Do not bypass login, CAPTCHA, paywalls, robots restrictions, anti-bot systems or contractual/API restrictions.

## Render
Start command:
`python app/server.py`

Render supplies `PORT` automatically.

The free Render filesystem/database is not guaranteed to be persistent across all redeploy/restart scenarios. The live engine therefore refreshes from the upstream feeds on startup and on the configured interval.

## Language flags
The language selector uses flag image assets from Flagcdn. If an environment blocks that CDN, the language still works but the flag images may not display.

## Launch checks
1. Deploy latest commit.
2. Open `/api/health`.
3. Open `/api/sources`.
4. Open `/api/events`.
5. Open the home page and test the language selector.
