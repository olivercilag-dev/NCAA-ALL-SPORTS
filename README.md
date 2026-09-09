# NCAA ALL SPORTS — ULTIMATE ULTIMATE

Final release with polished Game Center, verified ESPN/public-source ingestion, multilingual UI, UTC chronological feed, and provider data sections.

NCAA ALL SPORTS — V7

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

V7 fixes the ESPN scoreboard parser to tolerate optional fields returned as strings and prevents one malformed optional field from dropping an entire feed/event. It preserves V6 official-source infrastructure and does not fabricate events.

## Final time-zone and official-source behavior
- UTC is the default and primary time zone.
- Users can choose any IANA time zone supported by the browser (with UTC first).
- Event dates, day grouping, event times and the live clock follow the selected zone; the original UTC timestamp remains visible in Game Center.
- Official school/schedule links are shown when a verified source provides them.
- When no verified official URL is available, Game Center provides a user-clicked public web search for the school's official athletics site/schedule. The application does not scrape search results, bypass access controls, or invent official URLs.

## ULTIMATE ULTIMATE Game Center
The Game Center is designed as a single information hub for each event: team profiles, logos, provider links, official-school/schedule search links, conference hub links, venue, UTC/local time, score/status, broadcasts, play-by-play, statistics, leaders, odds, win probability, news and raw provider data when the authorized/public source actually supplies them.

Unavailable fields are shown as unavailable rather than fabricated. The project does not claim that one free public source contains every NCAA school or every sport. To add additional schools/conferences, add only verified public/authorized feeds or links permitted by their terms.

## FINAL LOCKED UI
The final UI uses a responsive athlete-and-logo hero artwork as the visual background of the main navigation/hero area, with the lower dashboard inspired by the approved sports-dashboard references. The implementation preserves the existing schedule, combined filters, timezone, multilingual, Game Center and data-engine features. Desktop, tablet and mobile breakpoints use dedicated artwork positioning/cropping so the hero remains proportionate.
