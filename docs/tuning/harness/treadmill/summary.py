"""One line per run of a batch, from each run's report.md, and the refusals and errors grouped by kind."""
import os, re, sys, collections
from pathlib import Path
out = Path(sys.argv[1])
kinds = collections.Counter(); examples = {}
rows = []
for report in sorted(out.glob("*/report.md")):
    text = report.read_text(); name = report.parent.name
    sec = lambda a, b: (re.search(rf"## {re.escape(a)}(.*?)(?=\n## {re.escape(b)}|\Z)", text, re.S) or [None, ""])[1]
    rpc = (report.parent / "rpc.jsonl").read_text() if (report.parent / "rpc.jsonl").exists() else ""
    finish = (re.findall(r'"finish":"([^"]*)"', rpc) or ["?"])[-1]
    wall = (re.search(r"wall ([^;]+);", text) or [None, "?"])[1]
    total = (re.search(r"Total tokens[^:]*: ([\d,]+)", text) or [None, "?"])[1]
    children = len(re.findall(r"^- \w+ [0-9a-f]{8} exit=", text, re.M))
    errors = sec("Errors and refusals (parent)", "Extension messages")
    for line in re.findall(r"^\d\d:\d\d:\d\d (\w+) ERROR: (.*)$", errors, re.M):
        tool, msg = line
        msg = re.sub(r"~?/[\w./@-]+", "<path>", msg); msg = re.sub(r"\d+", "N", msg)
        key = f"{tool}: {msg[:70]}"
        kinds[key] += 1; examples.setdefault(key, name)
    nerr = len(re.findall(r" ERROR: ", errors))
    audit = sec("Site audit (view's own checks, run on what was left)", "\x00")
    # "DIFF" only when a repeated part really has several versions. The comparison's other remarks - a
    # picture nothing uses, a page nothing links to - and its closing "unless a difference is meant" used
    # to print DIFF too, on sites whose navigation and footer were identical (batches 2 to 5).
    if re.search(r"^\s*- (?:header|navigation|footer|nav)\b[^\n]*\b\d+ versions", audit, re.M):
        same = "DIFF"
    elif re.search(r"have the same|The same on every page:", audit):
        same = "same" + ("+notes" if re.search(r"no page uses|no page links", audit) else "")
    else:
        same = "-"
    pages = len(re.findall(r"^- .*\.html \(", audit, re.M))
    images = len(re.findall(r"^- .*\.(?:jpe?g|png|webp|svg|gif) \(", audit, re.M))
    notes = sec("Page notes", "Image files that are not images").strip() if "### Page notes" in audit else ""
    notes = (re.search(r"### Page notes\n(.*?)\n### ", audit, re.S) or [None, ""])[1].strip()
    bad = (re.search(r"### Image files that are not images\n(.*)", audit, re.S) or [None, ""])[1].strip()
    dialogs = (re.findall(r'"dialogs":(\d+)', rpc) or ["?"])[-1]
    # How the top session's last turn ended: "aborted" with notices after it is a session that never woke.
    last = "?"
    batch = out.name[1:]
    work = Path(os.environ.get("TREADMILL_WORK") or Path.home() / "sandbox")
    sessions = sorted((work / f"b{batch}-{name}/.pi/sessions").glob("*.jsonl"))
    if sessions:
        import json
        stops = [(json.loads(l).get("message") or {}).get("stopReason") for l in sessions[0].read_text().splitlines() if '"stopReason"' in l]
        last = (stops or ["?"])[-1]
    if last != "stop": finish = f"{finish} (last turn: {last})"
    rows.append((name, finish, wall, total, children, nerr, dialogs, pages, images, same,
                 "ok" if notes in ("", "(none)") else "NOTES", "ok" if bad in ("", "(none)") else "BAD"))
print("| run | finish | wall | tokens | children | errors | dialogs | pages | images | nav/footer | page notes | image files |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in rows: print("| " + " | ".join(str(x) for x in r) + " |")
print("\n## Errors and refusals by kind\n")
for key, n in kinds.most_common(): print(f"- {n}x {key}   (e.g. {examples[key]})")
