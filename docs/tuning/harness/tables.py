"""The tables in docs/tuning/README.md, computed from the evidence files beside it.

    python3 docs/tuning/harness/tables.py            print every table
    python3 docs/tuning/harness/tables.py NAME       print one

tests/test_tuning_evidence.py regenerates each table and checks README.md still
shows it, so a number in the README cannot drift from the runs it came from.
"""
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DAY = HERE / "2026-11-11"


def load(name):
    return json.loads((DAY / name).read_text())


def passed(rows):
    return f"{sum(r['pass'] for r in rows)}/{len(rows)}"


def false_claims(rows):
    """Failed with no tool call at all: the reply claimed work nothing did."""
    return sum(1 for r in rows if not r["pass"] and r["tool_calls"] == 0)


def median_s(rows):
    return f"{statistics.median(r['seconds'] for r in rows):.1f} s"


def first_ab():
    rows = load("ab-rounds-1-3.json")
    out = ["| Model | Passed | Median per task | Failed with no tool call |", "|---|---|---|---|"]
    for model, label in (("qwen", "Qwen"), ("mistral", "Mistral (as first added)"), ("llama", "Llama")):
        rs = [r for r in rows if r["model"] == model]
        out.append(f"| {label} | {passed(rs)} | {median_s(rs)} | {false_claims(rs)} |")
    return "\n".join(out)


MISTRAL_ARMS = (
    ("guidance.json", "mistral", "As first added (temperature 1.0)"),
    ("guidance.json", "mistral+md", "1.0 and written rules against false claims"),
    ("temperature-0.15.json", "mistral@0.15", "Temperature 0.15"),
    ("guard-reasoning-vibe.json", "mistral@0.15+guard", "0.15 and the claim guard"),
    ("guard-reasoning-vibe.json", "mistral@0.15+vibe+guard", "0.15, Vibe's rules and the claim guard"),
    ("guard-reasoning-vibe.json", "mistral-high@0.7+guard", "Reasoning on, 0.7, and the claim guard"),
    ("guidance.json", "qwen", "Qwen, for reference"),
)


def mistral_settings():
    out = ["| Mistral, as set up | First 11 | Later 6 | All 17 | Failed with no tool call | Guard fired (then passed) | Median |",
           "|---|---|---|---|---|---|---|"]
    for name, arm, label in MISTRAL_ARMS:
        rs = [r for r in load(name) if r["arm"] == arm]
        first = [r for r in rs if not r["held_out"]]
        later = [r for r in rs if r["held_out"]]
        fired = [r for r in rs if r.get("guard_fired")]
        guard = f"{len(fired)} ({sum(r['pass'] for r in fired)})" if "guard" in arm else "-"
        out.append(f"| {label} | {passed(first) if first else '-'} | {passed(later)} | {passed(rs)} | "
                   f"{false_claims(rs)} | {guard} | {median_s(rs)} |")
    return "\n".join(out)


def compaction():
    data = load("compaction.json")
    out = ["| | Qwen | Mistral | Llama |", "|---|---|---|---|"]
    for kind, label in (("real", f"Real session (of {len(data['real']['facts'])} facts)"),
                        ("generated", f"Generated session (of {len(data['generated']['facts'])} facts)")):
        cells = []
        for model in ("qwen", "mistral", "llama"):
            runs = [r for r in data[kind]["runs"] if r["model"] == model]
            cells.append(", ".join(str(len(r["facts_kept"])) for r in sorted(runs, key=lambda r: r["round"])))
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    cells = []
    for model in ("qwen", "mistral", "llama"):
        secs = [r["seconds"] for kind in ("real", "generated") for r in data[kind]["runs"] if r["model"] == model]
        cells.append(f"{min(secs):.0f}-{max(secs):.0f} s")
    out.append("| Time per summary | " + " | ".join(cells) + " |")
    return "\n".join(out)


def suggestions():
    data = load("suggestions.json")
    key, verdict = data["blind_order"], data["blind_verdict_written_before_unblinding"]
    wins = {"qwen": 0, "mistral": 0, "tie": 0}
    failed = {"qwen": 0, "mistral": 0}
    for row, v in verdict.items():
        # A request that failed is not a quality judgement: it is counted on its own line.
        broken = [m for m in ("qwen", "mistral") if data["rows"][int(row)][m][0].get("error")]
        for m in broken:
            failed[m] += 1
        if not broken:
            wins["tie" if v == "tie" else key[int(row)]["AB".index(v)]] += 1
    lat = {m: statistics.median(a["seconds"] for r in data["rows"] for a in r[m] if a.get("seconds") is not None)
           for m in ("qwen", "mistral")}
    return ("| | Qwen | Mistral | Tie |\n|---|---|---|---|\n"
            f"| Better suggestion, judged blind | {wins['qwen']} | {wins['mistral']} | {wins['tie']} |\n"
            f"| Request failed (HTTP 400) | {failed['qwen']} | {failed['mistral']} | |\n"
            f"| Median time | {lat['qwen']:.2f} s | {lat['mistral']:.2f} s | |")


def temperature():
    data = load("temperature-probe.json")
    out = ["| 12 answers, random number 1-100 | Distinct |", "|---|---|"]
    for label, answers in data["mistral"].items():
        out.append(f"| Mistral, {label} | {len(set(answers))} |")
    out.append(f"| Qwen, server default | {len(set(data['qwen']['server default']))} |")
    return "\n".join(out)


def output_length():
    probes = load("gateway-probes.json")
    q, m = probes["long-qwen"], probes["forced-mistral"]
    return ("| | Qwen | Mistral |\n|---|---|---|\n"
            f"| One streamed reply | {q['usage']['completion_tokens']:,} tokens, finish `{q['finish_reason']}` | "
            f"{m['usage']['completion_tokens']:,} tokens, finish `{m['finish_reason']}` |\n"
            f"| Time | {q['seconds']:.0f} s | {m['seconds']:.0f} s |")


TABLES = {"first-ab": first_ab, "mistral-settings": mistral_settings, "compaction": compaction,
          "suggestions": suggestions, "temperature": temperature, "output-length": output_length}

if (DAY / "tuning.json").exists():
    def tuning():
        rows = load("tuning.json")
        arms = json.loads((DAY / "tuning-arms.json").read_text())
        out = ["| Arm | Settings | Passed | The 8 hard tasks | Failed with no tool call | Median | Input tokens per task |",
               "|---|---|---|---|---|---|---|"]
        for arm, spec in arms.items():
            rs = [r for r in rows if r["arm"] == arm]
            if not rs:
                continue
            hard = [r for r in rs if r["hard"]]
            tokens = statistics.median(r["input_tokens"] for r in rs)
            out.append(f"| {arm} | {spec['settings']} | {passed(rs)} | {passed(hard)} | {false_claims(rs)} | "
                       f"{median_s(rs)} | {tokens / 1000:.0f}K |")
        return "\n".join(out)
    TABLES["tuning"] = tuning


if (DAY / "sweep.json").exists():
    def sweep():
        rows = load("sweep.json")
        arms = json.loads((DAY / "sweep-arms.json").read_text())
        out = ["| Model | Temperature | Passed | The 8 hard tasks | Failed with no tool call | Median | Input tokens per task |",
               "|---|---|---|---|---|---|---|"]
        for arm, spec in sorted(arms.items(), key=lambda kv: (kv[1]["model"], kv[1]["temperature"])):
            rs = [r for r in rows if r["arm"] == arm]
            if not rs:
                continue
            hard = [r for r in rs if r["hard"]]
            shipped = " (shipped)" if spec.get("shipped") else ""
            tokens = statistics.median(r["input_tokens"] for r in rs)
            out.append(f"| {spec['label']} | {spec['temperature']}{shipped} | {passed(rs)} | {passed(hard)} | "
                       f"{false_claims(rs)} | {median_s(rs)} | {tokens / 1000:.0f}K |")
        return "\n".join(out)
    TABLES["sweep"] = sweep


DAY2 = HERE / "2026-11-12"


def sampling(batch):
    """One batch of the sampling sweep: each arm against the control it ran beside, pair by pair."""
    import paired
    rows = json.loads((DAY2 / f"sampling-batch{batch}.json").read_text())
    arms = json.loads((DAY2 / f"sampling-batch{batch}-arms.json").read_text())
    against = {c["arm"]: c for c in paired.compare(rows)}
    out = ["| Model | Settings | Passed | The 25 hardest | Against the control, pair by pair | p | "
           "Failed with no tool call | Median | Input tokens per task |",
           "|---|---|---|---|---|---|---|---|---|"]
    for arm, spec in sorted(arms.items(), key=lambda kv: (kv[1]["model"], kv[1]["role"] != "control",
                                                         kv[1]["role"] != "repeat", kv[0])):
        rs = [r for r in rows if r["arm"] == arm]
        if not rs:
            continue
        hardest = [r for r in rs if r["set"] == "hard2"]
        tokens = statistics.median(r["input_tokens"] for r in rs)
        if spec["role"] == "control":
            settings, versus, p = f"{spec['settings']} (shipped)", "-", "-"
        else:
            c = against[arm]
            settings = "the same again" if spec["role"] == "repeat" else f"**{spec['varies']} {spec['value']}**"
            versus = (f"{c['difference_points']:+.1f} points ({c['arm_only']} pairs better, "
                      f"{c['control_only']} worse, of {c['pairs']})")
            p = f"{c['p']:.2f}"
        out.append(f"| {spec['label']} | {settings} | {passed(rs)} | {passed(hardest)} | {versus} | {p} | "
                   f"{false_claims(rs)} | {median_s(rs)} | {tokens / 1000:.0f}K |")
    return "\n".join(out)


for _batch in ("1", "2"):
    if (DAY2 / f"sampling-batch{_batch}.json").exists():
        TABLES[f"sampling-{_batch}"] = lambda b=_batch: sampling(b)


if (DAY2 / "mistral-top-p-confirmation.json").exists():
    def mistral_top_p():
        """The confirmation run, read by the rule its plan fixed beforehand (paired.confirm)."""
        import paired
        rows = json.loads((DAY2 / "mistral-top-p-confirmation.json").read_text())
        c = paired.confirm(rows, "mistral-topp0.8", "mistral-ctrl")
        lo, hi = c["bootstrap"]["ci95_points"]
        def arm_rows(name):
            return [r for r in rows if r["arm"].partition("@")[0] == name]
        out = ["| Mistral, reasoning high | Passed | The 25 hardest | Median | Input tokens per task |", "|---|---|---|---|---|"]
        for name, label in (("mistral-ctrl", "temperature 0.7 (shipped)"), ("mistral-topp0.8", "temperature 0.7, **top_p 0.8**")):
            rs = arm_rows(name)
            hardest = [r for r in rs if r["set"] == "hard2"]
            out.append(f"| {label} | {passed(rs)} | {passed(hardest)} | {median_s(rs)} | "
                       f"{statistics.median(r['input_tokens'] for r in rs) / 1000:.0f}K |")
        out += ["", "| Pair by pair | top_p 0.8 against the shipped setting |", "|---|---|",
                f"| Pairs (gateway errors left out) | {c['pairs']} |",
                f"| Better, worse | {c['arm_only']}, {c['control_only']} |",
                f"| Difference | {c['difference_points']:+.1f} points |",
                f"| Exact McNemar p | {c['p']:.3f} |",
                f"| 95% interval, resampling whole tasks | {lo:+.1f} to {hi:+.1f} points |",
                f"| By the rule written beforehand | {'ships' if c['ships'] else 'does not ship'} |"]
        return "\n".join(out)
    TABLES["mistral-top-p"] = mistral_top_p



DAY3 = HERE / "2026-11-14"


def prompt_floor():
    """What one request costs before any work: one probe per flag, same empty project."""
    d = json.loads((DAY3 / "prompt-floor.json").read_text())["floor"]
    base = d["probes"][0]["first_request_input"]
    out = ["| Flags | First request | Difference | What the difference is |", "|---|---|---|---|"]
    for p in d["probes"]:
        diff = p["first_request_input"] - base
        out.append(f"| {p['label']} | {p['first_request_input']:,} | "
                   f"{'-' if diff == 0 else f'{diff:+,}'} | {p['what']} |")
    return "\n".join(out)


def c10_batch():
    """Two sessions of ten stock coding problems: passes, cost, and what the work used."""
    d = json.loads((DAY3 / "prompt-floor.json").read_text())["batch"]
    out = ["| Run | Problems | Wall | Input | Output | Requests | Tool errors | Dialogs | Sub-agents |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in d["runs"]:
        out.append(f"| {r['id']} | {r['passed']}/{r['problems']} | {r['wall']} | {r['input']:,} | {r['output']:,} | "
                   f"{r['requests']} | {r['tool_errors']} | {r['dialogs']} | {r['children']} |")
    return "\n".join(out)


TABLES["prompt-floor"] = prompt_floor
TABLES["c10"] = c10_batch

if __name__ == "__main__":
    for name in sys.argv[1:] or TABLES:
        print(f"<!-- table:{name} -->\n{TABLES[name]()}\n<!-- /table:{name} -->\n")
