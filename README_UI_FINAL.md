# NCAA ALL SPORTS — Simplified Pro UI

This build locks the visual direction around three principles:

1. **The homepage is simple:** large athlete hero, sport navigation, clean filters, and a compact schedule.
2. **Match rows show only what users need:** time, sport, school/team logos, team names, score/status, and a clear **Game Center** action.
3. **Game Center is the information destination:** the selected game opens into the full available dataset, including team profiles, logos, competition/conference, venue, score/status, broadcasts, links, statistics, leaders, play-by-play, news, odds/win probability when supplied, and a data-availability view.

Game Center always starts from the verified local event payload. Optional provider enrichment is attempted with a timeout, but a provider/API outage cannot prevent the Game Center from opening.

The hero uses the expanded multi-sport athlete artwork and is responsive across desktop, tablet and mobile layouts.
