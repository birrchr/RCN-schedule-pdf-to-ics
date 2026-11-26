# Curling schedule → calendar (.ics)

Turn an **RCN (Navy) Curling Club** "My Personal Schedule" PDF (printed from curlnavy.com) into an `.ics` file you can import into Google Calendar, Outlook or Apple Calendar.

- **Website** – drop your PDF in, download your calendar. Runs entirely in the browser; the PDF is never uploaded.
- **Python script** – same output from the command line.

## For club members

1. On curlnavy.com, open **My Schedule** → **Print** → **Save as PDF**.
2. Open the website, choose the PDF, click **Download calendar file**.
3. Import the `.ics` into your calendar app.

Each event:

| Field | Value |
|---|---|
| Title | `Curling: <League> vs <Opponent> (<Sheet>)` |
| Start | Game time, Ottawa time (`America/Toronto`) |
| End | Start + 120 min (doubles: 90 min) – adjustable |
| Location | `RCN (Navy) Curling Club, Ottawa - <Sheet>` |
| Notes | Every column: League, Round, Game Time, Flight, Loc, Versus |

Event IDs are stable (player + league + start time). Re-importing an updated schedule therefore updates existing games in most apps instead of duplicating them. A game moved to a new time shows up as a new event, so delete the old one by hand.

## Repository layout

```
docs/                       ← the website (served by GitHub Pages)
  index.html
  schedule.js               ← parsing + iCalendar logic
  vendor/pdfjs/             ← Mozilla pdf.js 4.10.38 (Apache-2.0), vendored so there's no CDN dependency
python/
  curling_schedule_to_ics.py
```

## Hosting on GitHub Pages (free)

1. Create a public repo (e.g. `curling-schedule-to-ics`) and push this folder to it.
2. In the repo, go to **Settings → Pages**.
3. Under **Build and deployment**, choose **Source: Deploy from a branch**, **Branch: `main`**, **Folder: `/docs`**, then click **Save**.
4. After a minute the site is live at `https://<your-username>.github.io/curling-schedule-to-ics/`.

The footer's "Source on GitHub" link finds the repo automatically when the site runs on github.io.

Other free static hosts (Cloudflare Pages, Netlify) also work: point them at the `docs` folder, with no build step.

## Python script

Requires Python 3.10+. With [uv](https://docs.astral.sh/uv/), dependencies install automatically:

```bash
uv run python/curling_schedule_to_ics.py printMySchedule.php.pdf
uv run python/curling_schedule_to_ics.py schedule.pdf -o games.ics --mixed-minutes 120 --doubles-minutes 90
```

Without uv: `pip install pypdf`, then `python python/curling_schedule_to_ics.py schedule.pdf`.

## Running the site locally

ES modules don't load from `file://`, so serve the folder:

```bash
cd docs && python -m http.server 8000   # then open http://localhost:8000
```

## If the club changes its PDF layout

Both versions match each schedule row with one regular expression: `ROW_RE` in `docs/schedule.js` and `python/curling_schedule_to_ics.py`. The expected row looks like:

```
Mixed Fixed: Weekend 1 Fri, Oct 2, 2026 5:30 pm A Sheet 4 Waterman
```

Please don't commit real schedule PDFs to the repo: they contain members' names.

## Disclaimer

This is an unofficial tool and is not affiliated with the RCN (Navy) Curling Club. Always check the club's official schedule.

## License

MIT (see `LICENSE`). pdf.js is © Mozilla, Apache-2.0 (`docs/vendor/pdfjs/LICENSE`).
