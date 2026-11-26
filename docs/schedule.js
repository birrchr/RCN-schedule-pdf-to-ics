// Shared parsing + iCalendar logic. Runs in the browser and in Node (for tests).
// Mirrors python/curling_schedule_to_ics.py.

export const CLUB = "RCN (Navy) Curling Club, Ottawa";
export const TZID = "America/Toronto";

// One schedule row, e.g.
//   Mixed Fixed: Weekend 1 Fri, Oct 2, 2026 5:30 pm A Sheet 4 Waterman
const ROW_RE = new RegExp(
  String.raw`^(?<league>.+?)\s+` +
  String.raw`(?<round>\d+)\s+` +
  String.raw`(?<when>(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s*[ap]m)\s+` +
  String.raw`(?:(?<flight>\S+)\s+)?` +
  String.raw`(?<loc>Sheet\s+\S+)` +
  String.raw`(?:\s+(?<versus>.*))?$`,
  "i"
);
const NAME_RE = /My Personal Schedule\s*\(([^)]+)\)/;
const MONTHS = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };

/** Rebuild text lines from a pdf.js document by grouping items on the same baseline. */
export async function pdfToLines(pdf) {
  const lines = [];
  for (let p = 1; p <= pdf.numPages; p++) {
    const page = await pdf.getPage(p);
    const { items } = await page.getTextContent();
    const rows = [];
    for (const it of items) {
      if (!it.str || !it.str.trim()) continue;
      const y = it.transform[5], x = it.transform[4];
      let row = rows.find(r => Math.abs(r.y - y) < 3);
      if (!row) rows.push(row = { y, parts: [] });
      row.parts.push({ x, s: it.str });
    }
    rows.sort((a, b) => b.y - a.y);
    for (const r of rows) {
      r.parts.sort((a, b) => a.x - b.x);
      lines.push(r.parts.map(q => q.s).join(" "));
    }
  }
  return lines;
}

/** Wall-clock date parts (Ottawa time) from "Fri, Oct 2, 2026 5:30 pm". */
function parseWhen(when) {
  const m = when.replace(/\s+/g, " ").match(/^\w{3}, (\w{3}) (\d{1,2}), (\d{4}) (\d{1,2}):(\d{2}) ?([ap]m)$/i);
  if (!m) return null;
  let h = +m[4] % 12;
  if (m[6].toLowerCase() === "pm") h += 12;
  return { y: +m[3], mo: MONTHS[m[1].toLowerCase()], d: +m[2], h, mi: +m[5] };
}

export function parseSchedule(lines) {
  const text = lines.join("\n");
  const nm = text.match(NAME_RE);
  const player = nm ? nm[1].trim() : null;
  const games = [];
  for (const raw of lines) {
    const line = raw.replace(/\s+/g, " ").trim();
    const m = line.match(ROW_RE);
    if (!m) continue;
    const g = Object.fromEntries(Object.entries(m.groups).map(([k, v]) => [k, (v || "").trim()]));
    g.loc = g.loc.replace(/\s+/g, " ");
    const start = parseWhen(g.when);
    if (!start) continue;
    games.push({ ...g, start });
  }
  return { player, games };
}

// Use a UTC Date purely as a wall-clock calculator (no time zone conversion).
const pad = n => String(n).padStart(2, "0");
function fmtLocal(dt) {
  return `${dt.getUTCFullYear()}${pad(dt.getUTCMonth() + 1)}${pad(dt.getUTCDate())}T${pad(dt.getUTCHours())}${pad(dt.getUTCMinutes())}00`;
}
const esc = s => s.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\n/g, "\\n");

function fold(line) {
  const enc = new TextEncoder();
  if (enc.encode(line).length <= 75) return line;
  const parts = []; let chunk = "", len = 0;
  for (const ch of line) {
    const n = enc.encode(ch).length;
    if (len + n > (parts.length ? 74 : 75)) { parts.push(chunk); chunk = ""; len = 0; }
    chunk += ch; len += n;
  }
  parts.push(chunk);
  return parts.join("\r\n ");
}

async function uid(seed) {
  const buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(seed));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 16) + "@curling-schedule";
}

export async function buildIcs({ player, games }, { mixedMinutes = 120, doublesMinutes = 90 } = {}) {
  const now = new Date();
  const stamp = `${now.getUTCFullYear()}${pad(now.getUTCMonth() + 1)}${pad(now.getUTCDate())}T${pad(now.getUTCHours())}${pad(now.getUTCMinutes())}${pad(now.getUTCSeconds())}Z`;
  const out = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//curling-schedule-to-ics//EN",
    "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
    `X-WR-CALNAME:${esc(player ? `Curling - ${player}` : "Curling schedule")}`, `X-WR-TIMEZONE:${TZID}`,
    "BEGIN:VTIMEZONE", `TZID:${TZID}`,
    "BEGIN:DAYLIGHT", "TZOFFSETFROM:-0500", "TZOFFSETTO:-0400", "TZNAME:EDT",
    "DTSTART:19700308T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT",
    "BEGIN:STANDARD", "TZOFFSETFROM:-0400", "TZOFFSETTO:-0500", "TZNAME:EST",
    "DTSTART:19701101T020000", "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD",
    "END:VTIMEZONE",
  ];
  for (const g of games) {
    const minutes = /doubles/i.test(g.league) ? doublesMinutes : mixedMinutes;
    const s = new Date(Date.UTC(g.start.y, g.start.mo, g.start.d, g.start.h, g.start.mi));
    const e = new Date(s.getTime() + minutes * 60000);
    const vs = g.versus || "TBD";
    const notes = [
      `League: ${g.league}`, `Round: ${g.round}`, `Game Time: ${g.when}`,
      `Flight: ${g.flight}`, `Loc: ${g.loc}`, `Versus: ${g.versus}`,
    ].join("\n");
    out.push(
      "BEGIN:VEVENT",
      `UID:${await uid(`${player ?? "None"}|${g.league}|${fmtLocal(s).slice(0, 13)}`)}`,
      `DTSTAMP:${stamp}`,
      `DTSTART;TZID=${TZID}:${fmtLocal(s)}`,
      `DTEND;TZID=${TZID}:${fmtLocal(e)}`,
      `SUMMARY:${esc(`Curling: ${g.league} vs ${vs} (${g.loc})`)}`,
      `LOCATION:${esc(`${CLUB} - ${g.loc}`)}`,
      `DESCRIPTION:${esc(notes)}`,
      "END:VEVENT",
    );
  }
  out.push("END:VCALENDAR");
  return out.map(fold).join("\r\n") + "\r\n";
}

export function fileNameFor(player) {
  return player ? `curling_${player.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_|_$/g, "").toLowerCase()}.ics` : "curling_schedule.ics";
}
