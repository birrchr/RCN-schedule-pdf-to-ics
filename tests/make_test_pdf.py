import sys
OUT = sys.argv[1] if len(sys.argv) > 1 else "sample_schedule.pdf"
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
"""Build a fake "My Personal Schedule" PDF (made-up names) laid out like the real one, with awkward cases:
non-numeric round, blank flight, TBA / Ice locations, multi-word flight and opponent, a wrapped league name, two pages."""
H = letter[1]
hdr = [("League",93),("Round",190),("Game Time",288),("Flight",406),("Loc",458),("Versus",518)]
col = [40,182,231,399,442,505]
rows = [
 ["Day Mens","1","Tue, Dec 1, 2026 9:30 am","A","Sheet 2","Smith"],
 ["Thursday Day Men's: Senior","2","Thu, Jan 7, 2027 1:00 pm","B","Sheet 4","O'Brien"],
 ["Ladies Evening","1","Mon, Nov 30, 2026 7:00 pm","","Sheet 1","Tremblay"],
 ["Masters 55+","3","Wed, Dec 2, 2026 12:00 pm","C","Sheet 3","Van der Berg"],
 ["Open: Doubles","1","Sun, Dec 6, 2026 6:00 pm","B","Sheet 2",""],
 ["Mixed Fixed: Weekend","Playoff","Sat, Mar 6, 2027 5:30 pm","A","Sheet 4","Burke"],
 ["Day Mens","1","Tue, Dec 15, 2026 9:30 am","A","TBA","Jones"],
 ["Day Mens","1","Tue, Dec 22, 2026 9:30 am","Gold","Ice 2","Jones Rink"],
 ["Wednesday Night","2","Wed, Jan 13, 2027 7:00 pm","A","Sheet 1","Patel"],  # wraps
]
c = canvas.Canvas(OUT, pagesize=letter)
def page(rs, pageno, wrap_idx=None):
    c.setFont("Helvetica-Bold", 11); c.drawString(380, H-49-9, "My Personal Schedule (Test Person)")
    c.setFont("Helvetica-Bold", 9)
    for t,x in hdr: c.drawString(x, H-76-8, t)
    c.setFont("Helvetica", 9); y = 92
    for i,r in enumerate(rs):
        for v,x in zip(r,col):
            if v: c.drawString(x, H-y-8, v)
        y += 16
        if i == wrap_idx:
            c.drawString(40, H-(y-5)-8, "Competitive"); y += 10
    c.drawString(40, 40, "Printed: 2026-11-25 21:30"); c.drawString(250, 40, "RCN (Navy) Curling Club"); c.drawString(540, 40, f"Page {pageno}")
    c.showPage()
page(rows[:5], 1); page(rows[5:], 2, wrap_idx=3)
c.save()
