# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdf>=4"]
# ///
"""
Convert an RCN (Navy) Curling Club "My Personal Schedule" PDF into an .ics calendar file.

Usage:
    uv run curling_schedule_to_ics.py printMySchedule.php.pdf
    uv run curling_schedule_to_ics.py schedule.pdf -o my_games.ics --mixed-minutes 120 --doubles-minutes 90

Without uv:  pip install pypdf  then  python curling_schedule_to_ics.py schedule.pdf

How to get the PDF: on curlnavy.com, open your personal schedule and choose Print -> Save as PDF.

Notes:
- All times are treated as Ottawa time (America/Toronto); DST is handled by the calendar app.
- The schedule only lists start times, so the end time is start + a duration you can set.
- Each event's notes hold every column: League, Round, Game Time, Flight, Loc, Versus.
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

from pypdf import PdfReader

CLUB = "RCN (Navy) Curling Club, Ottawa"
TZID = "America/Toronto"

# One schedule row, e.g.
#   Mixed Fixed: Weekend 1 Fri, Oct 2, 2026 5:30 pm A Sheet 4 Waterman
ROW_RE = re.compile(
    r"^(?P<league>.+?)\s+"
    r"(?P<round>\d+)\s+"
    r"(?P<when>(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s*[ap]m)\s+"
    r"(?:(?P<flight>\S+)\s+)?"          # flight may be blank
    r"(?P<loc>Sheet\s+\S+)"
    r"(?:\s+(?P<versus>.*))?$",          # opponent may be blank (e.g. a bye)
    re.IGNORECASE,
)
NAME_RE = re.compile(r"My Personal Schedule\s*\(([^)]+)\)")

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


def parse_pdf(path: Path) -> tuple[str | None, list[dict]]:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    m = NAME_RE.search(text)
    player = m.group(1).strip() if m else None
    games = []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if (m := ROW_RE.match(line)):
            g = {k: (v or "").strip() for k, v in m.groupdict().items()}
            g["start"] = datetime.strptime(re.sub(r"\s+", " ", g["when"]).upper(),
                                           "%a, %b %d, %Y %I:%M %p")
            games.append(g)
    return player, games


def build_ics(player: str | None, games: list[dict], mixed_min: int, doubles_min: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cal_name = f"Curling - {player}" if player else "Curling schedule"
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//curling-schedule-to-ics//EN",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
           f"X-WR-CALNAME:{esc(cal_name)}", f"X-WR-TIMEZONE:{TZID}", *VTIMEZONE]
    for g in games:
        minutes = doubles_min if "doubles" in g["league"].lower() else mixed_min
        start, end = g["start"], g["start"] + timedelta(minutes=minutes)
        vs = g["versus"] or "TBD"
        notes = "\n".join([
            f"League: {g['league']}", f"Round: {g['round']}", f"Game Time: {g['when']}",
            f"Flight: {g['flight']}", f"Loc: {g['loc']}", f"Versus: {g['versus']}",
        ])
        uid_seed = f"{player}|{g['league']}|{start:%Y%m%dT%H%M}"
        uid = hashlib.sha1(uid_seed.encode()).hexdigest()[:16] + "@curling-schedule"
        out += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;TZID={TZID}:{start:%Y%m%dT%H%M%S}",
            f"DTEND;TZID={TZID}:{end:%Y%m%dT%H%M%S}",
            f"SUMMARY:{esc('Curling: ' + g['league'] + ' vs ' + vs + ' (' + g['loc'] + ')')}",
            f"LOCATION:{esc(CLUB + ' - ' + g['loc'])}",
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

    player, games = parse_pdf(args.pdf)
    if not games:
        print("No games found - is this the 'My Personal Schedule' PDF?", file=sys.stderr)
        return 1

    out = args.output or Path(
        f"curling_{re.sub(r'[^A-Za-z0-9]+', '_', player).strip('_').lower()}.ics" if player else "curling_schedule.ics"
    )
    out.write_text(build_ics(player, games, args.mixed_minutes, args.doubles_minutes),
                   encoding="utf-8", newline="")
    print(f"Wrote {len(games)} games for {player or 'unknown player'} to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
