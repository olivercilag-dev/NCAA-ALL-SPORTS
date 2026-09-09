# NCAA ALL SPORTS — V6

# NCAA ALL SPORTS — V4

Live chronological NCAA event dashboard.

V4 normalizes ESPN/internal sport keys, stores the same event from multiple authorized sources under one canonical event key, keeps UTC times, excludes tennis, and never invents unavailable events.

Deploy on Render with `python app/server.py`.

# NCAA ALL SPORTS — LIVE BUILD v2

Responsive multi-sport NCAA schedule feed for phone and PC.

## Live features
- Yesterday / Today / Tomorrow / Next 7 Days
- UTC times
- Search and sport filter
- Event details with source and confidence
- Automatic refresh
- SQLite cache
- `/api/health`, `/api/events`, `/api/sources`, `/api/stats`
- Local flag SVG assets for 11 languages; no external flag CDN required
- Hebrew / עברית uses RTL
- Baseball included; Tennis excluded

## Data engine
The server uses public ESPN site scoreboard endpoints for the sports configured in `app/server.py`, plus optional authorized JSON feeds through environment variables. The application does not create fake events. Old `SEED` rows are deleted on startup.

A technically reachable public endpoint is not automatically a license to redistribute its data. Follow each provider's Terms of Service, API limits, attribution and redistribution rules. For commercial/public redistribution, use a feed whose license explicitly permits it.

Optional environment variables:
- `NCAA_SCHEDULE_URL`, `NCAA_API_KEY`
- `OFFICIAL_SCHEDULE_URL`, `OFFICIAL_API_KEY`
- `REFRESH_MINUTES`
- `DATABASE_PATH`

## Render
Build: `pip install -r requirements.txt`
Start: `python app/server.py`

## First launch checks
1. `/api/health`
2. `/api/sources`
3. `/api/stats`
4. `/api/events`
5. Home page + language selector


V6 adds verified official-school source support for public/authorized JSON and iCalendar feeds, preserves official school/schedule/event links, and exposes provider PBP/Gamecast/Summary/Box Score links when supplied. No source URL is fabricated and access controls are not bypassed.
