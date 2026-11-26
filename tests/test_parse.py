"""Run with:  uv run --with pdfplumber --with reportlab --with pytest pytest tests"""
import subprocess, sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "python"))
from curling_schedule_to_ics import parse_pdf, build_ics  # noqa: E402


def test_awkward_layouts(tmp_path):
    pdf = tmp_path / "sample.pdf"
    subprocess.run([sys.executable, str(HERE / "make_test_pdf.py"), str(pdf)], check=True)
    player, columns, games = parse_pdf(pdf)

    assert player == "Test Person"
    assert columns == ["League", "Round", "Game Time", "Flight", "Loc", "Versus"]
    assert len(games) == 9
    by_league = {(g["League"], g["start"]): g for g in games}

    assert by_league[("Day Mens", datetime(2026, 12, 1, 9, 30))]["Loc"] == "Sheet 2"
    assert games[2]["Flight"] == ""                                  # blank flight
    assert games[4]["Versus"] == ""                                  # no opponent listed
    assert games[5]["Round"] == "Playoff"                            # non-numeric round
    assert games[6]["Loc"] == "TBA"
    assert (games[7]["Flight"], games[7]["Loc"], games[7]["Versus"]) == ("Gold", "Ice 2", "Jones Rink")
    assert games[8]["League"] == "Wednesday Night Competitive"      # wrapped onto two lines

    ics = build_ics(player, columns, games, 120, 90)
    assert ics.count("BEGIN:VEVENT") == 9
    assert "DTSTART;TZID=America/Toronto:20261201T093000" in ics
    assert "DTEND;TZID=America/Toronto:20261206T193000" in ics       # doubles = 90 min
