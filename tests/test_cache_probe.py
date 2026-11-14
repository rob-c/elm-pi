"""The ELM prefix-cache tests (docs/tuning/harness/cache/) measure what they say they measure.

ELM reports no cache figures, so reuse is timed from outside. A timing test that calls any gateway
"cached" is worse than none, so each of the four is run here against two stand-in gateways - one that
answers a prompt it has seen the start of quickly, one that never does - and must tell them apart. The
fifth test reads what pi itself sent; its log writer and its reader are checked on requests that do and
do not extend the one before.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from extension_harness import node  # noqa: E402

CACHE = ROOT / "docs/tuning/harness/cache"
spec = importlib.util.spec_from_file_location("cache_probe", CACHE / "cache_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

COLD_S, WARM_S = 0.25, 0.01


class StandIn:
    """A gateway that takes COLD_S to read a prompt, or WARM_S when it has seen its first half before -
    for `ttl` seconds, or never if `caches` is false. With `servers` > 1 the requests are dealt out in
    turn to that many servers, each remembering only what it was sent itself: ELM as it looked on 2026-11-14."""

    def __init__(self, caches, ttl=60.0, servers=1):
        memories = [{} for _ in range(servers)]     # per server: prompt -> when
        outer = self
        self.requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                prompt = json.dumps(body["messages"])
                seen = memories[len(outer.requests) % servers]
                outer.requests.append(body)
                now = time.time()
                half = prompt[: len(prompt) // 2]
                warm = caches and any(old.startswith(half) and now - when < ttl for old, when in seen.items())
                time.sleep(WARM_S if warm else COLD_S)
                seen[prompt] = time.time()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for chunk in ({"choices": [{"delta": {"content": "OK"}}]},
                              {"choices": [], "usage": {"prompt_tokens": len(prompt) // 4, "completion_tokens": 1, "total_tokens": 1}}):
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/api/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class TimingTests(unittest.TestCase):
    def setUp(self):
        self.saving = probe.WARM_SAVING_S
        probe.WARM_SAVING_S = 0.1       # the stand-in's cold read is a quarter of a second, not ELM's three
        self.addCleanup(setattr, probe, "WARM_SAVING_S", self.saving)

    def run_test(self, name, caches, gaps=(0.3,), ttl=60.0, servers=1):
        gateway = StandIn(caches, ttl, servers)
        self.addCleanup(gateway.close)
        results = probe.run(gateway.base, "not-a-key", ["qwen"], [name], 400, list(gaps), seed=7)
        return results["models"]["qwen"][name], gateway

    def test_1_repeat_tells_a_gateway_that_reuses_a_prefix_from_one_that_does_not(self):
        reused, gateway = self.run_test("repeat", True)
        self.assertTrue(reused["reused"])
        self.assertEqual((8, 8, 1.0, 0), (reused["warm"], reused["of"], reused["hit_rate"], reused["misses_before_settling"]))
        self.assertLess(reused["repeat_s"], reused["cold_s"] / 2)
        self.assertEqual(["cold"] + ["repeat"] * 8 + ["cold"], [r["kind"] for r in reused["runs"]])
        # the closing cold request is a different prefix of the same size: without it, a gateway that was
        # merely slow on its first request of the day would pass
        first, last = (json.dumps(gateway.requests[i]["messages"]) for i in (0, 9))
        self.assertNotEqual(first[:200], last[:200])
        self.assertLess(abs(len(first) - len(last)) / len(first), 0.05)
        never = self.run_test("repeat", False)[0]
        self.assertEqual((False, 0, None), (never["reused"], never["warm"], never["repeat_s"]))

    def test_1b_a_cold_repeat_on_a_gateway_with_several_servers_is_counted_not_taken_for_no_cache(self):
        """The first live run: Mistral's first repeat and Llama's third were as slow as a cold request."""
        three, _ = self.run_test("repeat", True, servers=3)
        self.assertTrue(three["reused"])
        self.assertEqual((6, 8), (three["warm"], three["of"]))           # two more servers to warm, then all hits
        self.assertEqual(2, three["misses_before_settling"])
        shared, _ = self.run_test("shared", True, servers=3)
        self.assertEqual((4, 4), (shared["warm"], shared["of"]))         # asked three times first: every server has it
        lifetime, _ = self.run_test("lifetime", True, gaps=(0.3,), servers=3)
        self.assertEqual(0.3, lifetime["longest_warm_gap_s"])

    def test_2_grow_compares_an_appended_conversation_with_one_whose_first_line_changes(self):
        reused, gateway = self.run_test("grow", True)
        self.assertTrue(reused["reused"])
        self.assertEqual((7, 7, 0), (reused["warm"], reused["of"], reused["control_warm"]))
        self.assertLess(reused["appended_s"], reused["first_line_changed_s"] / 2)
        appended = [json.dumps(r["messages"]) for r in gateway.requests[:8]]
        for before, after in zip(appended, appended[1:]):           # each request extends the last, as pi's do
            self.assertTrue(after.startswith(before[:-1]))
        changed = [json.dumps(r["messages"]) for r in gateway.requests[8:]]
        self.assertEqual(8, len({c[:60] for c in changed}))          # and in the other arm none does
        never = self.run_test("grow", False)[0]
        self.assertEqual((False, 0), (never["reused"], never["warm"]))

    def test_3_lifetime_reports_the_longest_gap_a_prefix_survived(self):
        result, _ = self.run_test("lifetime", True, gaps=(0.3, 1.6), ttl=1.0)
        self.assertEqual([True, False], [c["warm"] for c in result["checks"]])
        self.assertEqual((0.3, 1.6), (result["longest_warm_gap_s"], result["shortest_cold_gap_s"]))
        self.assertTrue(result["reused"])
        for check in result["checks"]:                               # each gap was really waited out
            self.assertGreaterEqual(check["waited_s"], check["gap_s"])
            self.assertEqual(4, check["primes_warm"])                # warmed before the wait began
        # one ask after the gap, not three: the first puts the prefix back, and a second ask would have
        # called an expired prefix warm - as the first version of this test did
        self.assertIsInstance(result["checks"][1]["again_s"], float)
        never, _ = self.run_test("lifetime", False, gaps=(0.3,))
        self.assertIsNone(never["longest_warm_gap_s"])
        self.assertFalse(never["reused"])

    def test_4_shared_sees_other_conversations_start_warm_on_the_first_ones_prefix(self):
        reused, gateway = self.run_test("shared", True)
        self.assertTrue(reused["reused"])
        self.assertEqual((4, 4), (reused["warm"], reused["of"]))
        self.assertLess(max(reused["other_conversations_s"]), reused["cold_s"] / 2)
        a, b, c = (gateway.requests[i]["messages"][0]["content"] for i in (0, 3, 4))
        self.assertEqual(a[: len(a) - 200], b[: len(a) - 200])       # the same prefix ...
        self.assertEqual(3, len({a, b, c}))                          # ... and another ending each time
        never = self.run_test("shared", False)[0]
        self.assertEqual((False, 0), (never["reused"], never["warm"]))

    def test_every_prefix_is_new_and_no_result_holds_prompt_text_or_the_key(self):
        result, gateway = self.run_test("repeat", True)
        self.assertNotEqual(probe.prefix(1, 400), probe.prefix(2, 400))
        saved = json.dumps(result)
        self.assertNotIn("calibration", saved)                       # a filler word
        self.assertNotIn("not-a-key", saved)
        source = (CACHE / "cache_probe.py").read_text()
        self.assertNotIn("print(key", source.replace(" ", ""))
        self.assertIn("os.urandom", source)                          # seeds drawn at run time: nothing is pre-warmed

    def test_every_elm_model_is_probed_by_default(self):
        models = json.loads((ROOT / "config/elm-pi.json").read_text())
        text = json.dumps(models)
        for name, entry in probe.MODELS.items():
            self.assertIn(entry["id"], text, name)
        self.assertEqual({"qwen", "mistral", "llama"}, set(probe.MODELS))


class SprintTests(unittest.TestCase):
    """Test 5: a pi session can be served from the cache only if each request begins with the last."""

    def log_of(self, payloads):
        binary = node()
        if not binary:
            self.skipTest("node is not installed")
        runner = """
import { pathToFileURL } from "node:url";
const [source, cwd, payloads] = process.argv.slice(1);
const mod = await import(pathToFileURL(source).href);
const handlers = {};
mod.default({ on: (name, fn) => { handlers[name] = fn; } });
for (const payload of JSON.parse(payloads)) {
  handlers.before_provider_request({ payload }, { cwd, model: { id: "m" } });
  handlers.after_provider_response({ status: 200 });
  handlers.provider_stream_event({});
}
handlers.session_shutdown();
console.log(JSON.stringify({ shared: mod.sharedPrefix("abcd", "abXd") }));
"""
        with tempfile.TemporaryDirectory() as cwd:
            run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", runner,
                                  str(CACHE / "cache_log.ts"), cwd, json.dumps(payloads)],
                                 capture_output=True, text=True, timeout=60)
            if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
                self.skipTest("this node cannot load TypeScript")
            self.assertEqual(0, run.returncode, run.stderr[-1500:])
            self.assertEqual(2, json.loads(run.stdout)["shared"])
            text = (Path(cwd) / ".pi/cache-log.jsonl").read_text()
        return [json.loads(line) for line in text.splitlines()], text

    def test_5_the_log_shows_which_requests_extended_the_one_before_and_where_one_did_not(self):
        system = {"role": "system", "content": "You are pi. SECRET-PROMPT-TEXT " + "x" * 400}
        turn = lambda i: [{"role": "user", "content": f"step {i}"}, {"role": "assistant", "content": f"done {i}"}]
        tools = [{"type": "function", "function": {"name": "bash"}}]
        grown = [system]
        payloads = []
        for i in range(4):
            grown = grown + turn(i)
            payloads.append({"model": "m", "messages": list(grown), "tools": tools})
        rewritten = [dict(system, content="Today is another day. " + system["content"])] + grown[1:] + turn(9)
        payloads.append({"model": "m", "messages": rewritten, "tools": tools})
        rows, text = self.log_of(payloads)
        self.assertEqual(5, len(rows))
        self.assertNotIn("SECRET-PROMPT-TEXT", text)                 # sizes and places, never the prompt
        self.assertEqual(0, rows[0]["previous_bytes"])
        for row in rows[1:4]:
            self.assertEqual(row["previous_bytes"], row["shared_prefix_bytes"])
            self.assertNotIn("first_difference", row)
            self.assertTrue(row["tools_same"])
        self.assertLess(rows[4]["shared_prefix_bytes"], 0.5 * rows[4]["previous_bytes"])
        self.assertEqual("messages[0] (system) of 9", rows[4]["first_difference"])
        for row in rows:
            self.assertIsNotNone(row["first_event_ms"])

        report = probe.sprint(rows)["m"]
        self.assertEqual((5, 4, 3), (report["requests"], report["compared"], report["extended_the_last"]))
        self.assertFalse(report["append_only"])
        self.assertEqual([{"n": 5, "shared": report["least_shared"], "first_difference": "messages[0] (system) of 9"}],
                         report["not_extensions"])
        self.assertTrue(probe.sprint(rows[:4])["m"]["append_only"])

    def test_5b_a_session_is_scored_by_how_many_of_its_extending_requests_came_back_warm(self):
        row = lambda n, ms, shared=1.0: {"event": "request", "n": n, "pid": 1, "model": "m", "bytes": 80_000 + n,
                                         "previous_bytes": 40_000, "shared_prefix_bytes": int(40_000 * shared), "first_event_ms": ms}
        rows = [dict(row(0, 2000), previous_bytes=0, shared_prefix_bytes=0)]
        rows += [row(1, 300), row(2, 2100), row(3, 350), row(4, 320), row(5, 1900), row(6, 310), row(7, 2000, shared=0.2)]
        report = probe.sprint(rows, {"m": 2.0})["m"]
        self.assertEqual((6, 4, 0.67), (report["could_be_warm"], report["warm"], report["hit_rate"]))   # n=7 could not be
        self.assertAlmostEqual(report["seconds_lost_to_misses"], (2.1 - 0.315) + (1.9 - 0.315), places=1)
        self.assertEqual(0.315, report["warm_s_median"])

    def test_time_to_first_token_is_set_against_new_bytes_and_against_all_bytes(self):
        # a gateway that reuses the prefix: time follows what is new, not how long the conversation has grown
        rows = [{"event": "request", "n": i, "model": "m", "bytes": 10_000 + 3_000 * i, "previous_bytes": 9_000 + 3_000 * i,
                 "shared_prefix_bytes": 9_000 + 3_000 * i - new, "first_event_ms": 100 + new // 10}
                for i, new in enumerate([0, 4000, 500, 6000, 200, 3000, 800, 5000])]
        report = probe.sprint(rows)["m"]
        self.assertGreater(report["follows_new_bytes_r"], 0.9)
        self.assertLess(abs(report["follows_all_bytes_r"]), 0.5)
        self.assertIsNone(probe.correlation([1, 1, 1], [1, 2, 3]))

    def test_the_log_is_a_harness_tool_and_never_part_of_an_install(self):
        self.assertFalse((ROOT / "templates/extensions/cache_log.ts").exists())
        self.assertNotIn("cache-log", (ROOT / "config/elm-pi.json").read_text())
        batch = (ROOT / "docs/tuning/harness/treadmill/batch.sh").read_text()
        self.assertIn('cp "$TREADMILL_EXTENSION" "$INST/agent/extensions/zz-', batch)


class Record(unittest.TestCase):
    """The live run of 2026-11-14, and the README's account of it, say the same thing."""

    def test_the_readme_table_is_the_record(self):
        record = json.loads((ROOT / "docs/tuning/2026-11-14/elm-cache.json").read_text())["models"]
        readme = (ROOT / "docs/tuning/README.md").read_text()
        names = {"qwen": "Qwen 3.5", "mistral": "Mistral Small 4", "llama": "Llama 3.3"}
        self.assertEqual(set(names), set(record))
        compared = warm = cold = 0
        for key, name in names.items():
            m = record[key]
            self.assertIn(m["id"], json.dumps(probe.MODELS))
            row = (f"| {name} | {m['repeat']['cold_s']:.1f} s | {m['repeat']['repeat_s']:.1f} s | {m['repeat']['warm']} of 8 | "
                   f"{m['grow']['warm']} of 7 | {m['lifetime']['longest_warm_gap_s'] // 60} min | {m['shared']['warm']} of 4 | "
                   f"{m['sprint']['extended_the_last']} of {m['sprint']['compared']} | {m['sprint']['warm']} of {m['sprint']['could_be_warm']} |")
            self.assertIn(row, readme)
            self.assertTrue(m["sprint"]["append_only"], name)            # what elm-pi answers for
            self.assertEqual(0, m["grow"]["control_warm"], name)         # and the control never passed
            self.assertEqual(0, m["repeat"]["reported_cached_tokens"])   # ELM reports none: hence the timing
            compared += m["sprint"]["compared"]
            warm += m["sprint"]["warm"]
            cold += m["sprint"]["could_be_warm"] - m["sprint"]["warm"]
        self.assertEqual((254, 47), (compared, cold))
        self.assertIn("47 of 254", (ROOT / "docs/tuning/TREADMILL.md").read_text())
        self.assertNotIn("calibration lattice", json.dumps(record))      # times and sizes, no prompt text


if __name__ == "__main__":
    unittest.main()
