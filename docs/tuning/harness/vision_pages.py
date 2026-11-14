"""The pages behind the image comparison of 2026-11-12, and their screenshots.

    python3 vision_pages.py OUT_DIR

Writes OUT_DIR/html (the charts, the shapes, the table and their changed copies),
OUT_DIR/site_before and OUT_DIR/site_after (test5's frog site, from
2026-11-12/vision-pages, with the planted changes in the after copy), then renders
every page to OUT_DIR/png with headless Chrome as elm-pi's `view` does: a throwaway
profile, nothing but this machine resolving. CHROME names the browser if it is not
at the macOS default or on PATH as google-chrome.

Known answers (vision_score.py): bars A-E = 12, 7, 19, 4, 15, D red; lines cross at
x = 3, "signal" orange and rising; 3 red circles, 2 blue squares, 4 green triangles;
muon 105.66 MeV, tau heaviest, proton the positive one, 4 rows. Planted changes:
b1 (home page) nav "Species" -> "Frog Types", navbar green -> blue, button
"Learn More About Frogs" -> "Explore Frogs", the 40% facts card removed; b2 (bars)
B 7 -> 11, title "run" -> "spill", E blue -> green; b3 (about page) nav Species and
Conservation swapped, "What Are Frogs?" -> "What Is a Frog?", "Scientific
Classification" -> "Taxonomy"; b4 the species page twice, unchanged.
"""
import html
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path(sys.argv[1])
SITE = Path(__file__).resolve().parents[1] / "2026-11-12/vision-pages"
BLUE = "#4682b4"


def page(body):
    return ('<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{margin:0;'
            f'font-family:Helvetica,Arial,sans-serif;background:#fff}}</style></head><body>{body}</body></html>')


def bars(title, values, colours):
    labels, w, h, x0, y0, bw, scale = "ABCDE", 900, 600, 100, 520, 110, 22
    s = [f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">',
         f'<text x="{w/2}" y="50" font-size="30" text-anchor="middle">{html.escape(title)}</text>',
         f'<line x1="{x0}" y1="{y0}" x2="{w-60}" y2="{y0}" stroke="#000"/><line x1="{x0}" y1="80" x2="{x0}" y2="{y0}" stroke="#000"/>',
         '<text x="30" y="300" font-size="22" transform="rotate(-90 30 300)" text-anchor="middle">Hits</text>']
    for t in range(0, 21, 5):
        y = y0 - t * scale
        s.append(f'<text x="{x0-12}" y="{y+6}" font-size="18" text-anchor="end">{t}</text>'
                 f'<line x1="{x0-5}" y1="{y}" x2="{x0}" y2="{y}" stroke="#000"/>')
    for i, (v, c) in enumerate(zip(values, colours)):
        x = x0 + 40 + i * 150
        s.append(f'<rect x="{x}" y="{y0-v*scale}" width="{bw}" height="{v*scale}" fill="{c}"/>')
        s.append(f'<text x="{x+bw/2}" y="{y0+30}" font-size="22" text-anchor="middle">{labels[i]}</text>')
    s.append("</svg>")
    return page("".join(s))


def lines():
    pt = lambda x, y: (100 + x * 120, 520 - y * 40)  # noqa: E731
    poly = lambda pts: " ".join(f"{a},{b}" for a, b in pts)  # noqa: E731
    sig = [pt(x, 1 + 1.5 * x) for x in range(7)]
    bkg = [pt(x, 10 - 1.5 * x) for x in range(7)]  # equal to the signal at x = 3
    s = ['<svg width="900" height="600" xmlns="http://www.w3.org/2000/svg">',
         '<line x1="100" y1="520" x2="860" y2="520" stroke="#000"/><line x1="100" y1="60" x2="100" y2="520" stroke="#000"/>',
         '<text x="480" y="580" font-size="22" text-anchor="middle">Energy (GeV)</text>',
         '<text x="35" y="290" font-size="22" transform="rotate(-90 35 290)" text-anchor="middle">Events</text>']
    s += [f'<text x="{100+x*120}" y="545" font-size="18" text-anchor="middle">{x}</text>' for x in range(7)]
    s += [f'<polyline points="{poly(sig)}" fill="none" stroke="#ff7f0e" stroke-width="4"/>',
          f'<polyline points="{poly(bkg)}" fill="none" stroke="#7b2cbf" stroke-width="4"/>',
          '<rect x="640" y="70" width="200" height="80" fill="#fff" stroke="#999"/>',
          '<line x1="655" y1="95" x2="695" y2="95" stroke="#ff7f0e" stroke-width="4"/><text x="705" y="102" font-size="20">signal</text>',
          '<line x1="655" y1="130" x2="695" y2="130" stroke="#7b2cbf" stroke-width="4"/><text x="705" y="137" font-size="20">background</text>',
          "</svg>"]
    return page("".join(s))


def shapes():
    items = [("c", 120, 120), ("t", 330, 90), ("s", 560, 140), ("c", 760, 110), ("t", 150, 330), ("c", 420, 300),
             ("t", 650, 330), ("s", 250, 480), ("t", 520, 480)]
    s = ['<svg width="900" height="600" xmlns="http://www.w3.org/2000/svg">']
    for k, x, y in items:
        if k == "c":
            s.append(f'<circle cx="{x}" cy="{y}" r="45" fill="#e3242b"/>')
        if k == "s":
            s.append(f'<rect x="{x-42}" y="{y-42}" width="84" height="84" fill="#1f4fd8"/>')
        if k == "t":
            s.append(f'<polygon points="{x},{y-48} {x-48},{y+40} {x+48},{y+40}" fill="#2e9e3e"/>')
    s.append("</svg>")
    return page("".join(s))


def table():
    rows = [("electron", "0.511", "−1"), ("muon", "105.66", "−1"), ("tau", "1776.9", "−1"), ("proton", "938.27", "+1")]
    cell = 'style="border:1px solid #333;padding:10px 24px'
    return page('<div style="padding:40px"><h2 style="font-size:28px">Particle properties</h2>'
                '<table style="border-collapse:collapse;font-size:24px"><tr>'
                + "".join(f'<th {cell};background:#eee">{h}</th>' for h in ("Particle", "Mass (MeV)", "Charge")) + "</tr>"
                + "".join("<tr>" + "".join(f'<td {cell}">{c}</td>' for c in r) + "</tr>" for r in rows)
                + "</table></div>")


def plant(after):
    index = after / "index.html"
    s = index.read_text()
    s = s.replace('<li><a href="species.html">Species</a></li>', '<li><a href="species.html">Frog Types</a></li>', 1)
    s = s.replace(">Learn More About Frogs</a>", ">Explore Frogs</a>", 1)
    s = s.replace("</head>", "<style>.navbar { background-color: #1e3a8a !important; }</style>\n</head>", 1)
    lines_ = s.split("\n")
    i = next(n for n, l in enumerate(lines_) if "40%" in l) - 1   # the facts card holding 40%
    j = i + 1
    while "</div>" not in lines_[j]:
        j += 1
    del lines_[i:j + 1]
    index.write_text("\n".join(lines_))
    about = after / "about.html"
    s = about.read_text()
    s = s.replace('        <li><a href="species.html">Species</a></li>\n        <li><a href="conservation.html">Conservation</a></li>',
                  '        <li><a href="conservation.html">Conservation</a></li>\n        <li><a href="species.html">Species</a></li>', 1)
    s = s.replace(">What Are Frogs?</h2>", ">What Is a Frog?</h2>", 1).replace(">Scientific Classification</h2>", ">Taxonomy</h2>", 1)
    about.write_text(s)


def chrome():
    for c in (os.environ.get("CHROME"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome"), shutil.which("chromium")):
        if c and Path(c).exists():
            return c
    sys.exit("no Chrome or Chromium: set CHROME")


def render(src, png, size):
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                        "--no-default-browser-check", f"--user-data-dir={profile}", f"--window-size={size}",
                        f"--screenshot={png}", "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1",
                        src.resolve().as_uri()], check=True, capture_output=True, timeout=120)


(OUT / "html").mkdir(parents=True, exist_ok=True)
(OUT / "png").mkdir(exist_ok=True)
pages = {"a1_bars": bars("Detector hits per run", [12, 7, 19, 4, 15], [BLUE, BLUE, BLUE, "#d62728", BLUE]),
         "a2_lines": lines(), "a3_shapes": shapes(), "a4_table": table(),
         "b2_bars_before": bars("Detector hits per run", [12, 7, 19, 4, 15], [BLUE, BLUE, BLUE, "#d62728", BLUE]),
         "b2_bars_after": bars("Detector hits per spill", [12, 11, 19, 4, 15], [BLUE, BLUE, BLUE, "#d62728", "#2ca02c"])}
for name, text in pages.items():
    (OUT / "html" / f"{name}.html").write_text(text)
for side in ("site_before", "site_after"):
    shutil.copytree(SITE, OUT / side, dirs_exist_ok=True)
plant(OUT / "site_after")
for name in pages:
    render(OUT / "html" / f"{name}.html", OUT / "png" / f"{name}.png", "900,600")
for png, src in (("a5_frog_index", "site_before/index.html"), ("b1_before", "site_before/index.html"),
                 ("b1_after", "site_after/index.html"), ("b3_before", "site_before/about.html"),
                 ("b3_after", "site_after/about.html"), ("b4_same_a", "site_before/species.html"),
                 ("b4_same_b", "site_before/species.html")):
    render(OUT / src, OUT / "png" / f"{png}.png", "1280,1600")
print("rendered", len(list((OUT / "png").glob("*.png"))), "images into", OUT / "png")
