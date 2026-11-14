"""Score vision_eval.py's results against the known answers.

    python3 vision_score.py RESULTS.json[l] [SUMMARY.json]

Prints the tables; with SUMMARY.json, writes the same numbers there.
"""
import json
import re
import statistics
import sys
from collections import defaultdict

raw = open(sys.argv[1]).read()
rows = json.loads(raw) if raw.lstrip().startswith("[") else [json.loads(l) for l in raw.splitlines() if l.strip()]
OUT = {"factual": {}, "layout_defect_named": {}, "consistency": {}, "speed": {}, "overall_factual": {}}


def last_json(text, key):
    dec = json.JSONDecoder()
    for i in [m.start() for m in re.finditer(r"\{", text)][::-1]:
        try:
            obj, _ = dec.raw_decode(text[i:])
        except ValueError:
            continue
        if isinstance(obj, dict) and key in obj:
            return obj
    return None


def norm(s):
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", str(s).lower()).split())


def num(v):
    try:
        return float(str(v).replace(",", "").strip().rstrip("%+"))
    except ValueError:
        return None


def stat_token(v):
    s = str(v).lower().replace(",", "").replace("+", "").replace("%", "").strip()
    if "everywhere" in s:
        return "everywhere"
    if s in ("350000000", "350m", "350 m", "350 million", "350000000.0"):
        return "350m"
    if s in ("7000", "7000.0"):
        return "7000"
    if s in ("40", "40.0"):
        return "40"
    return s


# the overflow itself, not merely the word "Everywhere"
DEFECT = re.compile(r"overflow|clip|cut off|truncat|spill|exceed|extends? beyond|not fit|doesn.t fit|overlap|overrun")

FIELDS = {
    "a1_bars": {"title": lambda v: norm(v) == "detector hits per run", "bar_count": lambda v: num(v) == 5,
                "tallest_bar_label": lambda v: norm(v) == "c", "tallest_bar_value": lambda v: num(v) is not None and abs(num(v) - 19) <= 0.5,
                "red_bar_label": lambda v: norm(v) == "d"},
    "a2_lines": {"x_axis_label": lambda v: norm(v) == "energy gev", "y_axis_label": lambda v: norm(v) == "events",
                 "rising_series": lambda v: norm(v) == "signal", "rising_series_colour": lambda v: "orange" in norm(v),
                 "crossing_x": lambda v: num(v) is not None and abs(num(v) - 3) <= 0.25},
    "a3_shapes": {"red_circles": lambda v: num(v) == 3, "blue_squares": lambda v: num(v) == 2,
                  "green_triangles": lambda v: num(v) == 4},
    "a4_table": {"muon_mass": lambda v: num(v) is not None and abs(num(v) - 105.66) < 0.01,
                 "heaviest_particle": lambda v: norm(v) == "tau", "positive_particle": lambda v: norm(v) == "proton",
                 "row_count": lambda v: num(v) == 4},
    "a5_frog_index": {
        "site_title": lambda v: norm(v) == "frog world",
        "nav_items": lambda v: isinstance(v, list) and [norm(x) for x in v] == ["home", "about frogs", "species", "conservation"],
        "active_nav_item": lambda v: norm(v) == "home",
        "stat_values": lambda v: isinstance(v, list) and {stat_token(x) for x in v} >= {"7000", "350m", "everywhere", "40"},
    },
}

PLANTED = {
    "b1_page_pair": {
        "nav renamed": lambda t: "frog types" in t,
        "navbar blue": lambda t: re.search(r"nav|header|top bar|menu bar|navigation", t) and "blue" in t,
        "button text": lambda t: "explore frogs" in t,
        # the facts card: named, or the facts/stat row said to have lost one (not some other section's cards)
        "card removed": lambda t: ("40" in t or "threatened" in t) or (re.search(r"fact|stat", t) and re.search(r"remov|missing|three|\b3\b|fewer|wider|width|no longer", t)),
    },
    "b2_chart_pair": {
        "B 7->11": lambda t: "11" in t and re.search(r"\bb\b", t),
        "title run->spill": lambda t: "spill" in t,
        "E blue->green": lambda t: "green" in t and re.search(r"\be\b", t),
    },
    "b3_subtle_pair": {
        "nav order swapped": lambda t: "conservation" in t and "species" in t,
        "heading what is a frog": lambda t: "what is a frog" in t,
        "heading taxonomy": lambda t: "taxonomy" in t,
    },
    # the same image twice: every difference listed is false
    "b4_identical_pair": {},
}

by = defaultdict(list)
for r in rows:
    if r.get("error"):
        continue
    by[(r["arm"], r["item"])].append(r)

arms = sorted({a for a, _ in by})
print("== factual questions: fields right / asked, over all rounds")
summary = defaultdict(dict)
for item, fields in FIELDS.items():
    line = [f"{item:15}"]
    for arm in arms:
        rs = by[(arm, item)]
        right = total = 0
        misses = defaultdict(int)
        for r in rs:
            obj = last_json(r["content"], next(iter(fields))) or {}
            for f, ok in fields.items():
                total += 1
                good = f in obj and bool(ok(obj[f]))
                right += good
                if not good:
                    misses[f"{f}={json.dumps(obj.get(f))[:40]}"] += 1
        summary[arm][item] = (right, total)
        OUT["factual"].setdefault(item, {})[arm] = {"right": right, "asked": total}
        line.append(f"{arm} {right}/{total}")
        if misses:
            line.append("[" + "; ".join(f"{k} x{v}" for k, v in sorted(misses.items(), key=lambda kv: -kv[1])[:3]) + "]")
    print("  ".join(line))

print("\n== layout defect on the frog page ('Everywhere' overflows its card): runs that name it")
for arm in arms:
    rs = by[(arm, "a5_frog_index")]
    hits = 0
    for r in rs:
        obj = last_json(r["content"], "layout_problems") or {}
        probs = obj.get("layout_problems") or []
        hits += bool(DEFECT.search(norm(" ".join(map(str, probs))))) if probs else 0
    print(f"  {arm:13} {hits}/{len(rs)}")
    OUT["layout_defect_named"][arm] = {"runs": len(rs), "named": hits}

print("\n== consistency: planted differences found, and differences claimed that are not there")
for item, planted in PLANTED.items():
    for arm in arms:
        rs = by[(arm, item)]
        found = defaultdict(int)
        fps, recalls, fp_examples = [], [], []
        for r in rs:
            obj = last_json(r["content"], "differences") or {}
            diffs = obj.get("differences") or []
            texts = [norm(" ".join(str(d.get(k, "")) for k in ("where", "before", "after"))) if isinstance(d, dict) else norm(d) for d in diffs]
            hit = {name for name, match in planted.items() if any(match(t) for t in texts)}
            for name in hit:
                found[name] += 1
            recalls.append(len(hit) / len(planted) if planted else 1.0)
            false = [t for t in texts if not any(match(t) for match in planted.values())]
            fps.append(len(false))
            fp_examples += false
        per = ", ".join(f"{n} {found[n]}/{len(rs)}" for n in planted)
        OUT["consistency"].setdefault(item, {})[arm] = {"runs": len(rs), "recall": round(statistics.mean(recalls), 3), "false_per_run": round(statistics.mean(fps), 2), "found": {n: found[n] for n in planted}}
        print(f"  {item:14} {arm:13} recall {statistics.mean(recalls):.2f}  false/run {statistics.mean(fps):.1f}  [{per}]")
        for ex in fp_examples[:4]:
            print(f"      false: {ex[:110]}")

print("\n== speed and size")
for arm in arms:
    rs = [r for (a, _), v in by.items() if a == arm for r in v]
    out = [(r.get("usage") or {}).get("completion_tokens", 0) for r in rs]
    OUT["speed"][arm] = {"runs": len(rs), "median_seconds": statistics.median(r["seconds"] for r in rs), "median_output_tokens": statistics.median(out)}
    print(f"  {arm:13} runs={len(rs)} median {statistics.median(r['seconds'] for r in rs):.1f}s  "
          f"median output tokens {statistics.median(out):.0f}  truncated={sum(r['finish'] != 'stop' for r in rs)}")
print("\n== overall factual accuracy")
for arm in arms:
    right = sum(v[0] for v in summary[arm].values()); total = sum(v[1] for v in summary[arm].values())
    print(f"  {arm:13} {right}/{total} = {right/total:.1%}")
    OUT["overall_factual"][arm] = {"right": right, "asked": total}
if len(sys.argv) > 2:
    open(sys.argv[2], "w").write(json.dumps(OUT, indent=1) + "\n")
