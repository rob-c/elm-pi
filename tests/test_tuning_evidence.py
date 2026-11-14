"""docs/tuning: the evidence behind the model settings, and the docs that quote it.

The settings elm-pi ships for each model were chosen on measurements, kept in
docs/tuning/<date>/. This checks that they stay connected:

  - every table in docs/tuning/README.md is what docs/tuning/harness/tables.py
    computes from the result files today;
  - the numbers INSTALL.md quotes are the same ones;
  - every decision in docs/tuning/decisions.json is what the templates ship, and
    names evidence that exists;
  - the result files are well formed: every run has its arm, task, verdict,
    timing and tool counts, and no key, home folder or scratch path leaked in;
  - the harness that produced them still compiles.
"""

import json
import statistics
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TUNING = ROOT / "docs/tuning"
DAY = TUNING / "2026-11-11"
HARNESS = TUNING / "harness"
README = (TUNING / "README.md").read_text()
INSTALL = (ROOT / "INSTALL.md").read_text()
DECISIONS = json.loads((TUNING / "decisions.json").read_text())["decisions"]
MODELS = json.loads((ROOT / "templates/models.json").read_text())["providers"]["elm"]["models"]
ENTRY = {"qwen": next(m for m in MODELS if m["id"] == "@QWEN_MODEL@"),
         "mistral": next(m for m in MODELS if m["id"] == "@MISTRAL_MODEL@")}
SETTINGS = json.loads((ROOT / "templates/settings.json").read_text())
TASK_MODELS = json.loads((ROOT / "templates/config/pi-task-models/config.json").read_text())
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())

# Imported without writing __pycache__ beside it: compiled files hold absolute paths.
sys.dont_write_bytecode = True
sys.path.insert(0, str(HARNESS))
import tables  # noqa: E402  (docs/tuning/harness/tables.py)

RUN_FILES = tuple(f"2026-11-11/{n}" for n in ("ab-rounds-1-3.json", "guidance.json", "temperature-0.15.json",
                                               "guard-reasoning-vibe.json", "tuning.json", "sweep.json"))
RUN_FILES += tuple(f"2026-11-12/sampling-batch{n}.json" for n in ("1", "2")
                   if (TUNING / f"2026-11-12/sampling-batch{n}.json").exists())
RUN_KEYS = {"task", "pass", "seconds", "tool_calls", "turns"}


class TableTests(unittest.TestCase):
    pass


def _table_in_readme(self, name):
    block = f"<!-- table:{name} -->\n{tables.TABLES[name]()}\n<!-- /table:{name} -->"
    body = tables.TABLES[name]()
    self.assertIn(body, README, f"README.md's {name} table no longer matches the evidence; regenerate it with "
                                f"python3 docs/tuning/harness/tables.py {name}")
    del block


for _name in tables.TABLES:
    setattr(TableTests, f"test_readme_{_name.replace('-', '_')}_table_matches_the_evidence",
            lambda self, n=_name: _table_in_readme(self, n))


class InstallQuotesTests(unittest.TestCase):
    """INSTALL.md's Mistral section quotes the same runs."""

    def arm(self, file, arm):
        return [r for r in json.loads((DAY / file).read_text()) if r["arm"] == arm]

    def frac(self, rows):
        return f"{sum(r['pass'] for r in rows)}/{len(rows)}"

    def test_every_mistral_arm_total_is_quoted(self):
        for file, arm, _label in tables.MISTRAL_ARMS:
            if arm == "qwen":
                continue
            with self.subTest(arm=arm):
                self.assertIn(self.frac(self.arm(file, arm)), INSTALL)

    def test_the_reasoning_arm_held_out_score_is_quoted(self):
        rows = [r for r in self.arm("guard-reasoning-vibe.json", "mistral-high@0.7+guard") if r["held_out"]]
        self.assertIn(f"**{self.frac(rows)}**", INSTALL)

    def test_the_first_eleven_comparison_is_quoted(self):
        reasoning = [r for r in self.arm("guard-reasoning-vibe.json", "mistral-high@0.7+guard") if not r["held_out"]]
        llama = [r for r in json.loads((DAY / "ab-rounds-1-3.json").read_text()) if r["model"] == "llama"]
        self.assertIn(f"reasoning-on Mistral passed {sum(r['pass'] for r in reasoning)} of {len(reasoning)}", INSTALL)
        self.assertIn(f"where Llama\npassed {sum(r['pass'] for r in llama)}", INSTALL)

    def test_the_compaction_rows_are_quoted(self):
        for line in tables.compaction().splitlines()[2:4]:
            cells = [c.strip() for c in line.strip("|").split("|")][1:]
            with self.subTest(row=line):
                self.assertIn(" | ".join(cells), INSTALL)


class DecisionTests(unittest.TestCase):
    pass


def _shipped(self, d):
    entry = ENTRY.get(d["model"])
    setting, value = d["setting"], d["value"]
    if setting == "samplingParams":
        self.assertEqual(value, entry["samplingParams"])
    elif setting == "samplingParamsByThinkingLevel":
        self.assertEqual(value, entry["samplingParamsByThinkingLevel"])
    elif setting == "maxTokens":
        self.assertEqual(value, entry["maxTokens"])
    elif setting == "compat.supportsDeveloperRole":
        self.assertEqual(value, entry["compat"]["supportsDeveloperRole"])
    elif setting == "compat.supportsLongCacheRetention":
        for model in ENTRY.values():
            self.assertEqual(value, model["compat"]["supportsLongCacheRetention"])
        self.assertIn("compat: { supportsLongCacheRetention: false }",
                      (ROOT / "templates/extensions/elm-shim.ts").read_text())
    elif setting == "modelThinkingLevels":
        self.assertEqual(value, SETTINGS["modelThinkingLevels"][f"elm/@{d['model'].upper()}_MODEL@"])
    elif setting == "SHIM_TEMPERATURE":
        shim = (ROOT / "shim/shim.py").read_text()
        self.assertIn(f'os.environ.get("SHIM_TEMPERATURE", "{value}")', shim)
    elif setting == "claim guard":
        self.assertTrue((ROOT / value).exists())
        self.assertIn(Path(value).name, CONFIG["requiredExtensions"])
    elif setting == "httpIdleTimeoutMs":
        self.assertEqual(value, SETTINGS["httpIdleTimeoutMs"])
        stall = json.loads((TUNING / "2026-11-12/stall-summary.json").read_text())
        self.assertGreaterEqual(value / 1000, 2 * stall["longest_wait_seconds"])   # twice the longest healthy wait
        self.assertLess(value / 1000, min(s["seconds"] for s in stall["stalls"]))   # shorter than any stall seen
    elif setting == "compaction fallback":
        self.assertEqual(value, TASK_MODELS["profiles"]["balanced"]["fallback"])
    else:
        self.fail(f"no check for decision {setting!r}: add one")


def _evidence_exists(self, d):
    self.assertTrue(d["evidence"], d["setting"])
    for rel in d["evidence"]:
        self.assertTrue((TUNING / rel).exists(), rel)
    self.assertRegex(d["date"], r"^\d{4}-\d{2}-\d{2}$")
    self.assertTrue(d["why"].strip())


for _i, _d in enumerate(DECISIONS):
    _slug = re.sub(r"[^a-z0-9]+", "_", f"{_d['model']}_{_d['setting']}".lower()).strip("_")
    setattr(DecisionTests, f"test_{_slug}_is_shipped", lambda self, d=_d: _shipped(self, d))
    setattr(DecisionTests, f"test_{_slug}_cites_evidence", lambda self, d=_d: _evidence_exists(self, d))


class EvidenceFileTests(unittest.TestCase):
    def test_every_file_parses(self):
        for path in TUNING.glob("20*/*.json"):
            with self.subTest(file=path.name):
                json.loads(path.read_text())

    def test_nothing_private_leaked(self):
        # The generated session replays this repository's own files, whose
        # examples include placeholder home folders: it is checked for the
        # rest, not for those.
        replayed = DAY / "compaction-generated-session.jsonl"
        for path in TUNING.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            text = path.read_text(errors="ignore")
            found = [m.group(0) for pattern in (r"/private/tmp/claude\S*", r"ELM_API_KEY=[^\s'\"$<]\S*",
                                                r"Bearer [A-Za-z0-9_\-]{12,}", r"/var/folders/\S+")
                     for m in [re.search(pattern, text)] if m]
            if path == replayed:
                found = [f for f in found if f.startswith("/private/tmp/claude")]
            else:
                m = re.search(r"/Users/(?!you\b|me\b|<)[a-z][\w.-]*", text)
                if m:
                    found.append(m.group(0))
            with self.subTest(file=str(path.relative_to(TUNING))):
                self.assertEqual([], found)

    def test_the_real_sessions_are_kept_as_scores_only(self):
        compaction = json.loads((DAY / "compaction.json").read_text())
        for run in compaction["real"]["runs"]:
            self.assertNotIn("summary", run)
        suggestions = json.loads((DAY / "suggestions.json").read_text())
        private = [r for r in suggestions["rows"] if "not kept" in r["session"]]
        self.assertEqual(2, len(private))
        for row in private:
            for model in ("qwen", "mistral"):
                self.assertTrue(all(set(a) <= {"seconds", "error", "shown"} for a in row[model]))


def _run_records(self, name):
    rows = json.loads((TUNING / name).read_text())
    self.assertGreater(len(rows), 0)
    for r in rows:
        self.assertLessEqual(RUN_KEYS, set(r), f"{name}: {r.get('task')}")
        self.assertIsInstance(r["pass"], bool)
        self.assertGreater(r["seconds"], 0)
        self.assertGreaterEqual(r["tool_calls"], 0)


def _three_runs_per_cell(self, name):
    rows = json.loads((TUNING / name).read_text())
    key = "arm" if "arm" in rows[0] else "model"
    cells = {}
    for r in rows:
        cells[(r[key], r["task"])] = cells.get((r[key], r["task"]), 0) + 1
    self.assertEqual({3}, set(cells.values()), f"{name}: not three runs of every arm and task")


for _name in RUN_FILES:
    _slug = re.sub(r"[^a-z0-9]+", "_", Path(_name).stem.lower()).strip("_")
    setattr(EvidenceFileTests, f"test_{_slug}_records_are_complete", lambda self, n=_name: _run_records(self, n))
    setattr(EvidenceFileTests, f"test_{_slug}_has_three_runs_per_cell", lambda self, n=_name: _three_runs_per_cell(self, n))


import paired  # noqa: E402  (docs/tuning/harness/paired.py)


class PairedStatisticsTests(unittest.TestCase):
    """docs/tuning/harness/paired.py: the test every arm-vs-control verdict rests on."""

    def test_mcnemar_known_values(self):
        self.assertEqual(1.0, paired.mcnemar(0, 0))
        self.assertEqual(1.0, paired.mcnemar(5, 5))
        self.assertAlmostEqual(2 / 1024, paired.mcnemar(10, 0))        # all ten discordant one way
        self.assertAlmostEqual(2 * 11 / 1024, paired.mcnemar(1, 9))    # P(X<=1), n=10, doubled
        self.assertAlmostEqual(paired.mcnemar(3, 8), paired.mcnemar(8, 3))

    def test_mcnemar_never_exceeds_one(self):
        for b in range(8):
            for c in range(8):
                with self.subTest(b=b, c=c):
                    self.assertLessEqual(paired.mcnemar(b, c), 1.0)

    def test_wilson_interval_brackets_the_rate(self):
        lo, hi = paired.wilson(72, 75)
        self.assertTrue(lo < 72 / 75 < hi <= 1.0)
        self.assertEqual((0.0, 0.0), paired.wilson(0, 0))

    def rows(self, arm, passes):
        return [{"arm": arm, "task": f"t{i}", "rep": 0, "pass": p, "set": "hard2" if i % 2 else "hard",
                 "tool_calls": 1, "seconds": 1.0, "input_tokens": 1000} for i, p in enumerate(passes)]

    def test_arms_are_paired_by_task_and_round(self):
        rows = self.rows("qwen-ctrl", [1, 1, 0, 0]) + self.rows("qwen-x", [1, 0, 1, 1])
        (c,) = paired.compare(rows)
        self.assertEqual((4, 3, 2, 2, 1, 25.0), (c["pairs"], c["arm_pass"], c["control_pass"], c["arm_only"],
                                                 c["control_only"], c["difference_points"]))

    def test_only_shared_pairs_count(self):
        rows = self.rows("qwen-ctrl", [1, 1]) + self.rows("qwen-x", [1, 1, 1, 1])
        self.assertEqual(2, paired.compare(rows)[0]["pairs"])

    def test_the_aa_control_is_compared_like_any_arm(self):
        rows = self.rows("mistral-ctrl", [1, 0]) + self.rows("mistral-ctrl2", [1, 1])
        self.assertEqual(["mistral-ctrl2"], [c["arm"] for c in paired.compare(rows)])

    def test_a_pair_touched_by_a_gateway_error_is_left_out(self):
        rows = self.rows("qwen-ctrl", [1, 1, 1]) + self.rows("qwen-x", [0, 1, 1])
        rows[3]["infra"] = True                       # qwen-x's first run ended on a 429
        (c,) = paired.compare(rows)
        self.assertEqual((2, 0, 0), (c["pairs"], c["arm_only"], c["control_only"]))
        self.assertEqual(3, paired.compare(rows, drop_infra=False)[0]["pairs"])
        self.assertEqual(1, paired.signals(rows)["qwen-x"]["gateway_error_endings"])

    def session(self, root, *messages):
        sessions = Path(root) / ".pi/sessions"
        sessions.mkdir(parents=True)
        (sessions / "s.jsonl").write_text("".join(json.dumps({"message": m}) + "\n" for m in messages))

    def test_a_run_whose_last_reply_is_an_error_ended_on_the_gateway(self):
        with tempfile.TemporaryDirectory() as root:
            self.session(root, {"role": "user"}, {"role": "assistant", "stopReason": "toolUse"},
                         {"role": "assistant", "stopReason": "error"})
            self.assertTrue(paired.ended_on_gateway_error(root, 0))

    def test_a_retried_error_followed_by_a_reply_did_not(self):
        with tempfile.TemporaryDirectory() as root:
            self.session(root, {"role": "assistant", "stopReason": "error"}, {"role": "assistant", "stopReason": "stop"})
            self.assertFalse(paired.ended_on_gateway_error(root, 0))
            self.assertTrue(paired.ended_on_gateway_error(root, 1))
            self.assertTrue(paired.ended_on_gateway_error(root, "timeout"))

    def test_replicates_become_rounds_and_pair_with_their_own_number(self):
        rows = [{"arm": a, "task": "t", "rep": rep, "pass": True} for a in ("m-ctrl", "m-ctrl@2", "m-x", "m-x@2")
                for rep in (0, 1)]
        folded = paired.fold_replicates(rows)
        self.assertEqual({"m-ctrl", "m-x"}, {r["arm"] for r in folded})
        self.assertEqual({0, 1, 2, 3}, {r["rep"] for r in folded if r["arm"] == "m-x"})
        by = {(r["replicate_of"], r["rep"]) for r in folded}
        self.assertIn(("m-ctrl@2", 1), by)       # round 0, second replicate
        self.assertIn(("m-x@2", 3), by)          # round 1, second replicate
        self.assertEqual(4, paired.compare(folded)[0]["pairs"])

    def test_the_task_bootstrap_centres_on_the_difference(self):
        rows = []
        for t in range(10):
            for rep in range(3):
                rows += [{"arm": "a", "task": f"t{t}", "rep": rep, "pass": t < 8},
                         {"arm": "c", "task": f"t{t}", "rep": rep, "pass": t < 6}]
        b = paired.task_bootstrap(rows, "a", ["c"], n=2000)
        self.assertEqual((30, 10, 20.0), (b["pairs"], b["tasks"], b["difference_points"]))
        lo, hi = b["ci95_points"]
        self.assertTrue(0 <= lo < 20 < hi <= 50, b)
        self.assertEqual(b, paired.task_bootstrap(rows, "a", ["c"], n=2000))   # seeded

    def test_a_difference_on_one_task_alone_is_not_shown_by_the_bootstrap(self):
        rows = []
        for t in range(10):
            for rep in range(3):
                rows += [{"arm": "a", "task": f"t{t}", "rep": rep, "pass": t == 0 or t > 5},
                         {"arm": "c", "task": f"t{t}", "rep": rep, "pass": t > 5}]
        lo, hi = paired.task_bootstrap(rows, "a", ["c"], n=2000)["ci95_points"]
        self.assertLessEqual(lo, 0)              # 3 of 3 pairs better, but all on one task

    def test_holm(self):
        self.assertEqual({"a": 0.03, "b": 0.08, "c": 0.5}, paired.holm({"a": 0.01, "b": 0.04, "c": 0.5}))
        self.assertEqual({"a": 0.04, "b": 0.04}, paired.holm({"a": 0.03, "b": 0.02}))   # never falls below the one before

    def test_any_arm_can_be_the_control_and_the_pairs_stay_the_same(self):
        rows = self.rows("m-ctrl", [1, 0, 0]) + self.rows("m-ctrl2", [1, 1, 0]) + self.rows("m-x", [1, 1, 1])
        rows[0]["infra"] = True                       # the first control's first run: gateway error
        against_repeat = {c["arm"]: c for c in paired.compare(rows, control="m-ctrl2")}
        self.assertEqual({"m-ctrl", "m-x"}, set(against_repeat))
        self.assertEqual((2, 1, 0), (against_repeat["m-x"]["pairs"], against_repeat["m-x"]["arm_only"],
                                     against_repeat["m-x"]["control_only"]))
        self.assertEqual({"m-ctrl"}, {c["control"] for c in paired.compare(rows)})

    def confirmation_rows(self, arm_passes, control_passes, tasks=20):
        rows = []
        for t in range(tasks):
            for rep in range(3):
                for i, suffix in enumerate(("", "@2", "@3")):
                    rows.append({"arm": f"m-x{suffix}", "task": f"t{t}", "rep": rep, "pass": arm_passes(t, rep, i)})
                    rows.append({"arm": f"m-ctrl{suffix}", "task": f"t{t}", "rep": rep, "pass": control_passes(t, rep, i)})
        return rows

    def test_the_rule_ships_a_clear_win_spread_over_tasks(self):
        rows = self.confirmation_rows(lambda t, rep, i: t < 16, lambda t, rep, i: t < 16 and not (t % 3 == 0 and i == rep))
        c = paired.confirm(rows, "m-x", "m-ctrl")
        self.assertEqual(180, c["pairs"])
        self.assertTrue(c["ships"], c)

    def test_the_rule_does_not_ship_a_win_on_one_task(self):
        rows = self.confirmation_rows(lambda t, rep, i: t < 10 or t == 19, lambda t, rep, i: t < 10)
        c = paired.confirm(rows, "m-x", "m-ctrl")
        self.assertLess(c["p"], 0.05)            # 9 of 9 discordant pairs one way...
        self.assertFalse(c["ships"], c)          # ...but all on one task

    def test_the_rule_does_not_ship_a_tie(self):
        rows = self.confirmation_rows(lambda t, rep, i: (t + i) % 2 == 0, lambda t, rep, i: (t + i + rep) % 2 == 0)
        self.assertFalse(paired.confirm(rows, "m-x", "m-ctrl")["ships"])

    def test_a_task_set_filter_keeps_only_that_set(self):
        rows = self.rows("qwen-ctrl", [1, 1, 1, 1]) + self.rows("qwen-x", [0, 0, 0, 0])
        self.assertEqual(2, paired.compare(rows, "hard2")[0]["pairs"])


DAY2 = TUNING / "2026-11-12"


@unittest.skipUnless((DAY2 / "sampling-batch1.json").exists() and (DAY2 / "sampling-batch2.json").exists(),
                     "sampling sweep results not stored")
class SamplingProseTests(unittest.TestCase):
    """The figures README.md's sampling section quotes in its text, recomputed by harness/paired.py."""

    @classmethod
    def setUpClass(cls):
        cls.b1 = json.loads((DAY2 / "sampling-batch1.json").read_text())
        cls.b2 = json.loads((DAY2 / "sampling-batch2.json").read_text())
        cls.text = " ".join(README.split())
        cls.vs = {c["arm"]: c for c in paired.compare(cls.b1)}
        cls.vs_repeat = {c["arm"]: c for c in paired.compare(cls.b1, control="mistral-ctrl2")}

    def quoted(self, phrase):
        self.assertIn(phrase, self.text)

    def test_gateway_error_counts(self):
        self.quoted(f"{sum(r['infra'] for r in self.b1)} of batch 1's {len(self.b1):,} runs and "
                    f"{sum(r['infra'] for r in self.b2)} of batch 2's {len(self.b2)}")
        pairs = sorted({c["pairs"] for c in paired.compare(self.b1) + paired.compare(self.b2)})
        self.quoted(f"hence {pairs[0]} or {pairs[1]} pairs")

    def test_qwen(self):
        qwen = [c for c in paired.compare(self.b1) + paired.compare(self.b2) if c["model"] == "qwen"]
        others = [c for c in qwen if c["arm"] != "qwen-ctrl2"]
        self.assertLessEqual(max(abs(c["difference_points"]) for c in others), 1.5)
        self.quoted(f"its own repeat {abs(self.vs['qwen-ctrl2']['difference_points'])} points off")
        pp0 = self.vs["qwen-pp0"]
        self.quoted(f"(at 0: {pp0['difference_points']:+.1f} points, p {pp0['p']:.2f})")
        hardest = [sum(r["pass"] for r in rows if r["arm"] == arm and r["set"] == "hard2")
                   for rows in (self.b1, self.b2) for arm in {r["arm"] for r in rows if r["arm"].startswith("qwen")}]
        self.quoted(f"{min(hardest)} to {max(hardest)} of 75 runs of the 25 hardest")

    def test_llama(self):
        self.quoted(f"{self.vs['llama-t0.3']['difference_points']:+.1f} and {self.vs['llama-t0.6']['difference_points']:+.1f}"
                    f" points, inside the {self.vs['llama-ctrl2']['difference_points']:+.1f}")

    def test_mistral(self):
        c = self.vs["mistral-topp0.8"]
        self.quoted(f"top_p 0.8 was {c['difference_points']:.1f} points ahead of its control ({c['arm_only']} pairs "
                    f"better, {c['control_only']} worse, p {c['p']:.2f})")
        self.quoted(f"control was itself {-self.vs_repeat['mistral-ctrl']['difference_points']:.1f} points behind its repeat")
        r = self.vs_repeat["mistral-topp0.8"]
        self.quoted(f"against the repeat top_p 0.8 is {r['difference_points']:+.1f} (p {r['p']:.2f})")
        b = paired.task_bootstrap(self.b1, "mistral-topp0.8", ["mistral-ctrl", "mistral-ctrl2"])
        lo, hi = b["ci95_points"]
        self.quoted(f"{b['difference_points']:+.1f} points, 95% interval {lo:.1f} to {hi:+.1f}")
        holm = paired.holm({c["arm"]: c["p"] for c in paired.compare(self.b1) if not c["arm"].endswith("ctrl2")})
        self.quoted(f"`paired.holm`: {holm['mistral-topp0.8']:.2f})")
        self.assertEqual(6, len(holm))
        self.quoted("six comparisons at once")

    def test_the_confirmation_figures(self):
        rows = json.loads((DAY2 / "mistral-top-p-confirmation.json").read_text())
        c = paired.confirm(rows, "mistral-topp0.8", "mistral-ctrl")
        lo, hi = c["bootstrap"]["ci95_points"]
        self.assertFalse(c["ships"])
        self.quoted("top_p 0.8 does not ship: "
                    f"{c['difference_points']:+.1f} points, p {c['p']:.2f}, and the interval, {lo:.1f} to {hi:+.1f}")
        per_arm = {}
        for r in rows:
            per_arm[r["arm"]] = per_arm.get(r["arm"], 0) + r["pass"]
        shipped = sorted(v for a, v in per_arm.items() if a.startswith("mistral-ctrl"))
        top_p = sorted(v for a, v in per_arm.items() if a.startswith("mistral-topp"))
        self.quoted(f"passed {shipped[0]}, {shipped[1]} and {shipped[2]} of 150 between them, a spread of "
                    f"{shipped[2] - shipped[0]} runs")
        self.quoted(f"the three top_p 0.8 arms, {top_p[0]} to {top_p[2]}")
        self.assertTrue(shipped[0] <= top_p[0] and top_p[2] <= shipped[2])
        self.assertIn(f"it was {c['difference_points']:.1f} points better with p {c['p']:.2f}", " ".join(INSTALL.split()))

    def test_the_confirmation_plan_came_before_its_run(self):
        plan = json.loads((DAY2 / "mistral-top-p-confirmation-plan.json").read_text())
        self.assertTrue(plan["written_before_the_run"])
        notes = DAY2 / "mistral-top-p-confirmation-notes.json"
        if notes.exists():
            self.assertLess(plan["written"], json.loads(notes.read_text())["started"])


class VisionEvidenceTests(unittest.TestCase):
    """2026-11-12, images: Qwen against Mistral. INSTALL.md's table is the summary's numbers."""

    SUMMARY = json.loads((TUNING / "2026-11-12/vision-summary.json").read_text())
    RESULTS = json.loads((TUNING / "2026-11-12/vision-results.json").read_text())
    ARMS = ("qwen-off", "mistral-high", "mistral-off")

    def install(self):
        return " ".join((ROOT / "INSTALL.md").read_text().split())

    def test_every_run_is_there_and_answered(self):
        self.assertEqual(3 * 9 * 5, len(self.RESULTS))
        self.assertEqual(set(self.ARMS), {r["arm"] for r in self.RESULTS})
        self.assertEqual([], [r for r in self.RESULTS if r.get("error") or r["finish"] != "stop"])
        self.assertEqual({0, 1, 2, 3, 4}, {r["rep"] for r in self.RESULTS})

    def row(self, label, cells):
        return f"| {label} | " + " | ".join(cells) + " |"

    def test_the_install_table_is_the_summary(self):
        s, text = self.SUMMARY, self.install()
        c = s["consistency"]
        changed = ("b1_page_pair", "b2_chart_pair", "b3_subtle_pair")
        rows = {
            "Reading the charts, table and page: answers right":
                [f"{s['overall_factual'][a]['right']}/{s['overall_factual'][a]['asked']}" for a in self.ARMS],
            "Counting the shapes":
                [f"{s['factual']['a3_shapes'][a]['right']}/{s['factual']['a3_shapes'][a]['asked']}" for a in self.ARMS],
            "Planted differences found, over the three changed pairs":
                [f"{round(100 * statistics.mean(c[i][a]['recall'] for i in changed))}%" for a in self.ARMS],
            "Differences reported that are not there, per comparison":
                [f"{statistics.mean(c[i][a]['false_per_run'] for i in c):.1f}" for a in self.ARMS],
            "... when the two images are the same page":
                [f"{c['b4_identical_pair'][a]['false_per_run']:.1f}" for a in self.ARMS],
            'The page\'s overflowing "Everywhere" card named, unasked':
                [f"{s['layout_defect_named'][a]['named']}/{s['layout_defect_named'][a]['runs']}" for a in self.ARMS],
            "Median time per request": [f"{s['speed'][a]['median_seconds']:.1f} s" for a in self.ARMS],
        }
        for label, cells in rows.items():
            with self.subTest(row=label):
                self.assertIn(self.row(label, cells), text)

    def test_the_recommendation_follows_the_numbers(self):
        c = self.SUMMARY["consistency"]
        false = {a: statistics.mean(c[i][a]["false_per_run"] for i in c) for a in self.ARMS}
        self.assertEqual("qwen-off", min(false, key=false.get))
        self.assertIn("Image description and consistency work therefore goes to `qwen`", self.install())


class HarnessTests(unittest.TestCase):
    def test_every_python_script_compiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            for path in HARNESS.glob("*.py"):
                with self.subTest(script=path.name):
                    py_compile.compile(str(path), cfile=str(Path(tmp) / (path.stem + ".pyc")), doraise=True)

    @unittest.skipUnless(shutil.which("node"), "needs node")
    def test_the_compaction_script_parses(self):
        result = subprocess.run(["node", "--check", str(HARNESS / "compact_test.mjs")], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_the_experiment_guard_and_the_shipped_one_agree_on_the_rule(self):
        # The shipped guard grew from the experiment's: same trigger, scoped to models.
        experiment = (HARNESS / "claim-guard.ts").read_text()
        shipped = (ROOT / "templates/extensions/claim-guard.ts").read_text()
        for text in (experiment, shipped):
            self.assertIn("agent_before_settle", text)
            self.assertIn("continue: true", text)


if __name__ == "__main__":
    unittest.main()


class StallEvidenceTests(unittest.TestCase):
    """2026-11-12, how long ELM goes silent: the README's table and INSTALL.md's figures are the summary's."""

    SUMMARY = json.loads((TUNING / "2026-11-12/stall-summary.json").read_text())
    NAMES = {"Qwen": "Qwen/Qwen3.5-397B-A17B-FP8", "Llama": "meta-llama/Llama-3.3-70B-Instruct",
             "Mistral": "mistralai/Mistral-Small-4-119B-2603"}

    def test_the_readme_table_is_the_summary(self):
        readme = (TUNING / "README.md").read_text()
        for name, model in self.NAMES.items():
            s = self.SUMMARY["short_reply_seconds"][model]
            with self.subTest(model=name):
                self.assertIn(f"| {name} | {s['n']:,} | {s['p50']}s | {s['p99']}s | {s['p999']}s | {s['max']}s |", readme)
                self.assertEqual(0, s["over"]["60"])            # "None waited past 60s"

    def test_install_quotes_the_summary(self):
        text = " ".join((ROOT / "INSTALL.md").read_text().split())
        s = self.SUMMARY
        self.assertIn(f"Measured over {s['corpus']['successful']:,} successful requests", text)
        self.assertIn(f"the longest wait before a reply began was {s['longest_wait_seconds']}s", text)
        self.assertIn(" and ".join(f"{x['seconds']}s" for x in s["stalls"]), text)

    def test_nothing_private_is_kept(self):
        raw = (TUNING / "2026-11-12/stall-summary.json").read_text()
        for marker in ("/Users/", "/home/", "/private/", "/var/folders", "sk-"):
            self.assertNotIn(marker, raw)
