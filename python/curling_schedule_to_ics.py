# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfplumber>=0.11"]
# ///
"""
Convert an RCN (Navy) Curling Club "My Personal Schedule" PDF into an .ics calendar file.

Usage:
    uv run curling_schedule_to_ics.py printMySchedule.php.pdf
    uv run curling_schedule_to_ics.py schedule.pdf -o my_games.ics --mixed-minutes 120 --doubles-minutes 90

Without uv:  pip install pdfplumber  then  python curling_schedule_to_ics.py schedule.pdf

How to get the PDF: on curlnavy.com, open your personal schedule and choose Print -> Save as PDF.

Notes:
- All times are treated as Ottawa time (America/Toronto); DST is handled by the calendar app.
- The schedule only lists start times, so the end time is start + a duration you can set.
- Works for any league: columns are found by their position under the header row
  (League, Round, Game Time, Flight, Loc, Versus), not by what the values look like.
  Each event's notes hold every column the PDF has, in order.
- UIDs are stable (based on league + start time), so re-importing an updated schedule
  updates existing events in most calendar apps instead of creating duplicates.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pdfplumber

CLUB = "RCN (Navy) Curling Club, Ottawa"
TZID = "America/Toronto"

NAME_RE = re.compile(r"My Personal Schedule\s*\(([^)]+)\)")
# "Fri, Oct 2, 2026 5:30 pm" (weekday and comma optional)
WHEN_RE = re.compile(
    r"(?:[A-Za-z]{3,9},?\s+)?(?P<mon>[A-Za-z]{3})[a-z]*\.?\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})"
    r"\s+(?P<h>\d{1,2}):(?P<mi>\d{2})\s*(?P<ampm>[ap])\.?m\.?",
    re.IGNORECASE,
)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

CELL_GAP = 10      # points; gaps wider than this separate columns, narrower ones separate words
ROW_TOL = 3        # points; words within this vertical distance are on the same line
WRAP_GAP = 1.6     # a non-game line closer than this many row heights to the game above is a wrapped cell


def parse_when(text: str) -> datetime | None:
    m = WHEN_RE.search(" ".join(text.split()))
    if not m or m["mon"][:3].lower() not in MONTHS:
        return None
    h = int(m["h"]) % 12 + (12 if m["ampm"].lower() == "p" else 0)
    return datetime(int(m["year"]), MONTHS[m["mon"][:3].lower()], int(m["day"]), h, int(m["mi"]))


def group_lines(words: list[dict]) -> list[dict]:
    """Group words into lines, and each line into cells split at wide horizontal gaps."""
    lines: list[dict] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(lines[-1]["top"] - w["top"]) <= ROW_TOL:
            lines[-1]["words"].append(w)
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        cells: list[dict] = []
        for w in sorted(line["words"], key=lambda w: w["x0"]):
            if cells and w["x0"] - cells[-1]["x1"] <= CELL_GAP:
                cells[-1]["text"] += " " + w["text"]
                cells[-1]["x1"] = w["x1"]
            else:
                cells.append({"text": w["text"], "x0": w["x0"], "x1": w["x1"]})
        line["cells"] = cells
        line["text"] = " ".join(c["text"] for c in cells)
    return lines


def is_header(line: dict) -> bool:
    t = line["text"].lower()
    return "league" in t and ("versus" in t or "opponent" in t) and len(line["cells"]) >= 3


def assign(cells: list[dict], columns: list[dict]) -> dict[str, str]:
    """Put each cell under the column whose header centre is nearest to the cell centre."""
    row = {c["name"]: "" for c in columns}
    for cell in cells:
        mid = (cell["x0"] + cell["x1"]) / 2
        col = min(columns, key=lambda c: abs(c["mid"] - mid))
        row[col["name"]] = (row[col["name"]] + " " + cell["text"]).strip()
    return row


def find_col(columns: list[str], *keys: str) -> str | None:
    for k in keys:
        for c in columns:
            if k in c.lower():
                return c
    return None


def parse_pdf(path: Path) -> tuple[str | None, list[str], list[dict]]:
    """Return (player name, column names, games). Each game maps column name -> text, plus 'start'."""
    player, columns, games = None, [], []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            lines = group_lines(page.extract_words())
            prev_game_line = None
            for line in lines:
                if player is None and (m := NAME_RE.search(line["text"])):
                    player = m.group(1).strip()
                if is_header(line):
                    columns = [{"name": c["text"], "mid": (c["x0"] + c["x1"]) / 2} for c in line["cells"]]
                    prev_game_line = None
                    continue
                if not columns:
                    continue
                row = assign(line["cells"], columns)
                names = [c["name"] for c in columns]
                time_col = find_col(names, "time", "date")
                start = parse_when(row[time_col]) if time_col else None
                if start is None:
                    # also accept separate Date + Time columns
                    start = parse_when(" ".join(row[n] for n in names if re.search("date|time", n, re.I)))
                if start:
                    row["start"] = start
                    games.append(row)
                    prev_game_line = line
                elif prev_game_line is not None and games and \
                        line["top"] - prev_game_line["top"] < WRAP_GAP * max(line["words"][0]["bottom"] - line["top"], 8):
                    # a long value wrapped onto a second line: append it to the game above
                    for k, v in row.items():
                        if v:
                            games[-1][k] = (games[-1][k] + " " + v).strip()
                else:
                    prev_game_line = None
    return player, [c["name"] for c in columns], games

VTIMEZONE = [
    "BEGIN:VTIMEZONE", f"TZID:{TZID}",
    "BEGIN:DAYLIGHT", "TZOFFSETFROM:-0500", "TZOFFSETTO:-0400", "TZNAME:EDT",
    "DTSTART:19700308T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT",
    "BEGIN:STANDARD", "TZOFFSETFROM:-0400", "TZOFFSETTO:-0500", "TZNAME:EST",
    "DTSTART:19701101T020000", "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD",
    "END:VTIMEZONE",
]


def esc(s: str) -> str:
    """Escape text per RFC 5545."""
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> str:
    """Fold lines longer than 75 octets per RFC 5545."""
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    parts, chunk = [], b""
    for ch in line:
        e = ch.encode("utf-8")
        if len(chunk) + len(e) > (75 if not parts else 74):
            parts.append(chunk.decode("utf-8"))
            chunk = b""
        chunk += e
    parts.append(chunk.decode("utf-8"))
    return "\r\n ".join(parts)


def build_ics(player: str | None, columns: list[str], games: list[dict],
              mixed_min: int, doubles_min: int) -> str:
    league_col = find_col(columns, "league", "event", "division")
    loc_col = find_col(columns, "loc", "sheet", "ice")
    vs_col = find_col(columns, "versus", "opponent", " vs")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cal_name = f"Curling - {player}" if player else "Curling schedule"
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//curling-schedule-to-ics//EN",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
           f"X-WR-CALNAME:{esc(cal_name)}", f"X-WR-TIMEZONE:{TZID}", *VTIMEZONE]
    for g in games:
        league = g.get(league_col, "") if league_col else ""
        loc = g.get(loc_col, "") if loc_col else ""
        vs = g.get(vs_col, "") if vs_col else ""
        minutes = doubles_min if "doubles" in league.lower() else mixed_min
        start, end = g["start"], g["start"] + timedelta(minutes=minutes)

        title = "Curling" + (f": {league}" if league else "") + f" vs {vs or 'TBD'}" + (f" ({loc})" if loc else "")
        notes = "\n".join(f"{c}: {g.get(c, '')}" for c in columns)   # every column, in PDF order
        uid_seed = f"{player}|{league}|{start:%Y%m%dT%H%M}"
        uid = hashlib.sha1(uid_seed.encode()).hexdigest()[:16] + "@curling-schedule"
        out += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;TZID={TZID}:{start:%Y%m%dT%H%M%S}",
            f"DTEND;TZID={TZID}:{end:%Y%m%dT%H%M%S}",
            f"SUMMARY:{esc(title)}",
            f"LOCATION:{esc(CLUB + (' - ' + loc if loc else ''))}",
            f"DESCRIPTION:{esc(notes)}",
            "END:VEVENT",
        ]
    out.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in out) + "\r\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path, help="schedule PDF printed from curlnavy.com")
    ap.add_argument("-o", "--output", type=Path, help="output .ics (default: curling_<name>.ics)")
    ap.add_argument("--mixed-minutes", type=int, default=120, help="length of non-doubles games (default 120)")
    ap.add_argument("--doubles-minutes", type=int, default=90, help="length of doubles games (default 90)")
    args = ap.parse_args()

    player, columns, games = parse_pdf(args.pdf)
    if not games:
        print("No games found - is this the 'My Personal Schedule' PDF?", file=sys.stderr)
        return 1

    out = args.output or Path(
        f"curling_{re.sub(r'[^A-Za-z0-9]+', '_', player).strip('_').lower()}.ics" if player else "curling_schedule.ics"
    )
    out.write_text(build_ics(player, columns, games, args.mixed_minutes, args.doubles_minutes),
                   encoding="utf-8", newline="")
    print(f"Wrote {len(games)} games for {player or 'unknown player'} to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
