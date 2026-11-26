// Shared parsing + iCalendar logic. Columns are found by position under the header row,
// so any league works.  Runs in the browser and in Node (for tests).
// Mirrors python/curling_schedule_to_ics.py.

export const CLUB = "RCN (Navy) Curling Club, Ottawa";
export const TZID = "America/Toronto";

const NAME_RE = /My Personal Schedule\s*\(([^)]+)\)/;
// "Fri, Oct 2, 2026 5:30 pm" (weekday and comma optional)
const WHEN_RE = /(?:[A-Za-z]{3,9},?\s+)?([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*([ap])\.?m\.?/i;
const MONTHS = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };

const CELL_GAP = 10;  // points; gaps wider than this separate columns
const ROW_TOL = 3;    // points; items within this vertical distance are on the same line
const WRAP_GAP = 1.6; // a non-game line closer than this many line heights to the game above is a wrapped cell

/** Wall-clock date parts (Ottawa time). */
export function parseWhen(text) {
  const m = text.replace(/\s+/g, " ").match(WHEN_RE);
  if (!m || !(m[1].slice(0, 3).toLowerCase() in MONTHS)) return null;
  const h = (+m[4] % 12) + (m[6].toLowerCase() === "p" ? 12 : 0);
  return { y: +m[3], mo: MONTHS[m[1].slice(0, 3).toLowerCase()], d: +m[2], h, mi: +m[5] };
}

/** Text items with positions (top-down coordinates) from every page of a pdf.js document. */
export async function pdfToPages(pdf) {
  const pages = [];
  for (let p = 1; p <= pdf.numPages; p++) {
    const page = await pdf.getPage(p);
    const { items } = await page.getTextContent();
    const words = [];
    for (const it of items) {
      if (!it.str || !it.str.trim()) continue;
      // split runs that contain spaces into words, spreading the width evenly by character
      const x = it.transform[4], top = -it.transform[5], cw = it.width / Math.max(it.str.length, 1);
      const re = /\S+/g; let m;
      while ((m = re.exec(it.str))) {
        words.push({ text: m[0], x0: x + m.index * cw, x1: x + (m.index + m[0].length) * cw, top, h: it.height || 8 });
      }
    }
    pages.push(words);
  }
  return pages;
}

function groupLines(words) {
  const lines = [];
  for (const w of [...words].sort((a, b) => a.top - b.top || a.x0 - b.x0)) {
    const last = lines[lines.length - 1];
    if (last && Math.abs(last.top - w.top) <= ROW_TOL) last.words.push(w);
    else lines.push({ top: w.top, words: [w] });
  }
  for (const line of lines) {
    const cells = [];
    for (const w of line.words.sort((a, b) => a.x0 - b.x0)) {
      const c = cells[cells.length - 1];
      if (c && w.x0 - c.x1 <= CELL_GAP) { c.text += " " + w.text; c.x1 = w.x1; }
      else cells.push({ text: w.text, x0: w.x0, x1: w.x1 });
    }
    line.cells = cells;
    line.text = cells.map(c => c.text).join(" ");
  }
  return lines;
}

const isHeader = l => /league/i.test(l.text) && /versus|opponent/i.test(l.text) && l.cells.length >= 3;

function assign(cells, columns) {
  const row = Object.fromEntries(columns.map(c => [c.name, ""]));
  for (const cell of cells) {
    const mid = (cell.x0 + cell.x1) / 2;
    const col = columns.reduce((best, c) => Math.abs(c.mid - mid) < Math.abs(best.mid - mid) ? c : best);
    row[col.name] = (row[col.name] + " " + cell.text).trim();
  }
  return row;
}

export function findCol(columns, ...keys) {
  for (const k of keys) for (const c of columns) if (c.toLowerCase().includes(k)) return c;
  return null;
}

/** -> { player, columns: [names], games: [{<column>: text, ..., start}] } */
export function parseSchedule(pages) {
  let player = null, columns = [];
  const games = [];
  for (const words of pages) {
    let prevGameLine = null;
    for (const line of groupLines(words)) {
      const nm = !player && line.text.match(NAME_RE);
      if (nm) player = nm[1].trim();
      if (isHeader(line)) {
        columns = line.cells.map(c => ({ name: c.text, mid: (c.x0 + c.x1) / 2 }));
        prevGameLine = null;
        continue;
      }
      if (!columns.length) continue;
      const row = assign(line.cells, columns);
      const names = columns.map(c => c.name);
      const timeCol = findCol(names, "time", "date");
      let start = timeCol ? parseWhen(row[timeCol]) : null;
      if (!start) start = parseWhen(names.filter(n => /date|time/i.test(n)).map(n => row[n]).join(" "));
      if (start) {
        games.push({ ...row, start });
        prevGameLine = line;
      } else if (prevGameLine && games.length &&
                 line.top - prevGameLine.top < WRAP_GAP * Math.max(line.words[0].h, 8)) {
        const g = games[games.length - 1];
        for (const [k, v] of Object.entries(row)) if (v) g[k] = (g[k] + " " + v).trim();
      } else {
        prevGameLine = null;
      }
    }
  }
  return { player, columns: columns.map(c => c.name), games };
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

export async function buildIcs({ player, columns, games }, { mixedMinutes = 120, doublesMinutes = 90 } = {}) {
  const leagueCol = findCol(columns, "league", "event", "division");
  const locCol = findCol(columns, "loc", "sheet", "ice");
  const vsCol = findCol(columns, "versus", "opponent", " vs");
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
    const league = leagueCol ? g[leagueCol] || "" : "";
    const loc = locCol ? g[locCol] || "" : "";
    const vs = vsCol ? g[vsCol] || "" : "";
    const minutes = /doubles/i.test(league) ? doublesMinutes : mixedMinutes;
    const s = new Date(Date.UTC(g.start.y, g.start.mo, g.start.d, g.start.h, g.start.mi));
    const e = new Date(s.getTime() + minutes * 60000);
    const title = "Curling" + (league ? `: ${league}` : "") + ` vs ${vs || "TBD"}` + (loc ? ` (${loc})` : "");
    const notes = columns.map(c => `${c}: ${g[c] ?? ""}`).join("\n"); // every column, in PDF order
    out.push(
      "BEGIN:VEVENT",
      `UID:${await uid(`${player ?? "None"}|${league}|${fmtLocal(s).slice(0, 13)}`)}`,
      `DTSTAMP:${stamp}`,
      `DTSTART;TZID=${TZID}:${fmtLocal(s)}`,
      `DTEND;TZID=${TZID}:${fmtLocal(e)}`,
      `SUMMARY:${esc(title)}`,
      `LOCATION:${esc(CLUB + (loc ? ` - ${loc}` : ""))}`,
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
