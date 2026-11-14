"""Does ELM reuse a prompt's prefix? Four timing tests against the gateway, per model.

ELM's replies carry no cache figures - `cacheRead` and `cacheWrite` were 0 in every one of 319 pi
session files on 2026-11-14 - so reuse cannot be read from a session. It can be timed: a request whose
long prefix the gateway has just processed should reach its first token sooner than one whose prefix is
new, by about the time it takes to read that prefix.

    python3 -I cache_probe.py ENVFILE OUT.json [--models qwen,mistral,llama] [--tests repeat,grow,lifetime,shared]
                                               [--prefix-words 9000] [--gaps 10,60,180,420] [--base URL]

The key is read from ENVFILE into memory only and is never printed or written. Every prefix is made
of random words from a seed drawn at run time, so nothing this sends has been sent before: a "cold"
request really is cold. OUT.json holds times, sizes and verdicts - no prompt text.

The tests (test 5, what pi itself sends, is cache_log.ts and `sprint` below):

  repeat    P cold, P again eight times, then a different prefix of the same length cold.
            Reports how many of the eight were warm (far faster than both cold ones).
  grow      A conversation that grows by a turn at a time, twice: once appended to (the prefix of each
            request is the whole previous request, as in a pi session) and once with its first line
            changed every turn (nothing reusable). Reports how many appended turns were warm.
  lifetime  One prefix per gap, each sent five times to warm it and once more after its gap.
            Reports the longest gap after which the prefix was still warm.
  shared    One conversation, then four more that start with the same long prefix and differ after
            it, as a parent and its sub-agents do. Reports how many of the four started warm.

Every verdict is a count, not a yes or no: ELM answers from more than one server and each has its own
cache, so a single repeat can be cold on a gateway that reuses prefixes and tells nothing.

    python3 -I cache_probe.py sprint LOG.jsonl OUT.json [TIMING.json ...]
            reads cache_log.ts's log of a pi session and reports, per model, how much of each request
            was a byte-for-byte extension of the one before, and whether time to first token followed
            the new bytes or the whole request.
"""
import json
import os
import random
import statistics
import sys
import time
import urllib.error
import urllib.request

MODELS = {
    "qwen": {"id": "Qwen/Qwen3.5-397B-A17B-FP8", "extra": {"reasoning_effort": "none"}},
    "mistral": {"id": "mistralai/Mistral-Small-4-119B-2603", "extra": {"reasoning_effort": "none"}},
    "llama": {"id": "meta-llama/Llama-3.3-70B-Instruct", "extra": {}},
}
WORDS = ("detector calibration lattice photon gradient baseline tensor residual vertex aperture coupling "
         "cascade threshold spectrum isotope momentum quartz plasma fringe scatter boson ferrite cathode "
         "dipole kernel manifold orbit phase quench raster solenoid torque vacuum wavelet yield zenith").split()

# A repeat counts as reused when it takes under this share of a cold request, and is at least this much faster.
WARM_RATIO = 0.6
WARM_SAVING_S = 0.4


def prefix(seed, words):
    """`words` random words, numbered in lines so that no two seeds share a long run."""
    rng = random.Random(seed)
    lines = []
    for i in range(0, words, 12):
        lines.append(f"{seed:x}-{i // 12}: " + " ".join(rng.choice(WORDS) for _ in range(12)))
    return "Reference notes follow. They are filler; do not summarise them.\n" + "\n".join(lines)


def is_warm(warm_s, cold_s):
    """Whether `warm_s` is what a reused prefix looks like next to `cold_s`."""
    return warm_s < WARM_RATIO * cold_s and cold_s - warm_s > WARM_SAVING_S


class Gateway:
    def __init__(self, base, key, timeout=300):
        self.base, self.key, self.timeout = base.rstrip("/"), key, timeout

    def ask(self, model, messages, max_tokens=4):
        """One streamed completion: seconds to the first chunk and to the end, sizes, and what usage says."""
        body = {"model": MODELS[model]["id"], "messages": messages, "max_tokens": max_tokens, "temperature": 0,
                "stream": True, "stream_options": {"include_usage": True}, **MODELS[model]["extra"]}
        data = json.dumps(body).encode()
        for attempt in range(6):
            req = urllib.request.Request(self.base + "/chat/completions", data=data, method="POST",
                                         headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            started = time.time()
            try:
                response = urllib.request.urlopen(req, timeout=self.timeout)
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:300]
                if e.code == 429 or e.code >= 500:        # a busy gateway is not a measurement
                    time.sleep(min(60, 2 ** attempt * 2))
                    continue
                return {"error": f"HTTP {e.code}: {detail}", "bytes": len(data)}
            except Exception as e:  # noqa: BLE001 - a probe reports whatever went wrong
                return {"error": f"{type(e).__name__}: {e}", "bytes": len(data)}
            first = first_text = None
            usage = None
            for raw in response:
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                    continue
                if first is None:
                    first = time.time() - started
                try:
                    chunk = json.loads(line[5:])
                except ValueError:
                    continue
                usage = chunk.get("usage") or usage
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if first_text is None and (delta.get("content") or delta.get("reasoning_content") or delta.get("reasoning")):
                        first_text = time.time() - started
            total = time.time() - started
            details = (usage or {}).get("prompt_tokens_details") or {}
            return {"first_s": round(first if first is not None else total, 3),
                    "first_text_s": round(first_text if first_text is not None else total, 3), "total_s": round(total, 3),
                    "bytes": len(data), "prompt_tokens": (usage or {}).get("prompt_tokens"),
                    # What a gateway that reports reuse would put here; ELM's has been absent or 0.
                    "cached_tokens": details.get("cached_tokens"), "usage_keys": sorted((usage or {}).keys()),
                    "retries": attempt}
        return {"error": "rate-limited six times running", "bytes": len(data)}


def seconds(result):
    return result.get("first_text_s") if "error" not in result else None


def ask_user(text):
    return {"role": "user", "content": text}


QUESTION = "\n\nReply with the single word OK."


def hits(times, cold_s):
    """How many of `times` are what a reused prefix looks like next to `cold_s`."""
    return sum(1 for t in times if t is not None and is_warm(t, cold_s))


# The first run of these tests (2026-11-14) found a repeat sometimes as slow as the first request - Mistral's
# first repeat, Llama's third, Qwen's second turn - and warm again on the next: what several servers, each
# with a cache of its own, look like from outside. So one repeat proves nothing either way: every test asks
# several times and reports how many were warm.
REPEATS = 8
ASKS = 3
PRIMES = 5


def test_repeat(gw, model, seeds, words):
    a, b = prefix(seeds(), words), prefix(seeds(), words)
    runs = [("cold", gw.ask(model, [ask_user(a + QUESTION)]))]
    runs += [("repeat", gw.ask(model, [ask_user(a + QUESTION)])) for _ in range(REPEATS)]
    runs.append(("cold", gw.ask(model, [ask_user(b + QUESTION)])))
    cold = [seconds(r) for kind, r in runs if kind == "cold" and seconds(r) is not None]
    again = [seconds(r) for kind, r in runs if kind == "repeat" and seconds(r) is not None]
    out = {"runs": [{"kind": kind, **r} for kind, r in runs]}
    if len(cold) == 2 and len(again) == REPEATS:
        warm = [t for t in again if is_warm(t, min(cold))]
        out.update(cold_s=round(statistics.mean(cold), 3), repeat_s=round(statistics.median(warm), 3) if warm else None,
                   warm=len(warm), of=REPEATS, hit_rate=round(len(warm) / REPEATS, 2),
                   # cold repeats before the last cold one: each is a server that had not seen the prefix
                   misses_before_settling=max((i + 1 for i, t in enumerate(again) if not is_warm(t, min(cold))), default=0),
                   reused=len(warm) >= 2,
                   reported_cached_tokens=max((r.get("cached_tokens") or 0) for _, r in runs))
    return out


def test_grow(gw, model, seeds, words, turns=8):
    """Appended to, each request extends the last; with its first line changed, none does."""
    base = prefix(seeds(), words)
    step = prefix(seeds(), max(120, words // 20))
    arms = {}
    for arm in ("appended", "first_line_changed"):
        messages, times = [], []
        for turn in range(turns):
            head = base if arm == "appended" else f"Run {seeds():x}.\n" + base
            if not messages:
                messages = [ask_user(head + QUESTION)]
            else:
                messages[0] = ask_user(head + QUESTION)
                messages += [{"role": "assistant", "content": "OK"}, ask_user(f"More filler {turn}:\n{step}{QUESTION}")]
            result = gw.ask(model, messages)
            times.append({"turn": turn, **result})
        arms[arm] = times
    out = {"arms": arms}
    later = lambda arm: [seconds(r) for r in arms[arm][1:] if seconds(r) is not None]
    if len(later("appended")) == turns - 1 and len(later("first_line_changed")) == turns - 1:
        changed = statistics.median(later("first_line_changed"))
        warm = [t for t in later("appended") if is_warm(t, changed)]
        out.update(appended_s=round(statistics.median(later("appended")), 3), first_line_changed_s=round(changed, 3),
                   warm=len(warm), of=turns - 1, hit_rate=round(len(warm) / (turns - 1), 2),
                   control_warm=hits(later("first_line_changed"), changed),
                   reused=len(warm) >= 2)
    return out


def test_lifetime(gw, model, seeds, words, gaps):
    """Each gap has its own prefix, so one check does not refresh another's. A prefix is sent PRIMES times
    to warm it (one send warms one server) and once after its gap. Once only: that ask puts the prefix
    back, so a second would be warm whether or not the first was."""
    cold = gw.ask(model, [ask_user(prefix(seeds(), words) + QUESTION)])
    primed = []
    for gap in gaps:
        text = prefix(seeds(), words) + QUESTION
        first = [gw.ask(model, [ask_user(text)]) for _ in range(PRIMES)]
        primed.append((gap, text, time.time(), first))
    checks = []
    for gap, text, primed_at, first in sorted(primed, key=lambda item: item[0]):
        wait = primed_at + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        waited = round(time.time() - primed_at, 1)
        again = seconds(gw.ask(model, [ask_user(text)]))
        cold_s = seconds(first[0])
        checks.append({"gap_s": gap, "waited_s": waited, "first_time_s": cold_s, "again_s": again,
                       "primes_warm": hits([seconds(r) for r in first[1:]], cold_s) if cold_s is not None else 0,
                       "warm": bool(cold_s is not None and again is not None and is_warm(again, cold_s)),
                       "error": first[0].get("error")})
    warm = [c["gap_s"] for c in checks if c["warm"]]
    cold_after = [c["gap_s"] for c in checks if not c["warm"]]
    return {"cold_s": seconds(cold), "checks": checks, "longest_warm_gap_s": max(warm) if warm else None,
            # a gap that came back cold while a longer one came back warm was not the cache expiring:
            # that ask reached a server the five primes had missed
            "shortest_cold_gap_s": min(cold_after) if cold_after else None, "reused": bool(warm)}


def test_shared(gw, model, seeds, words, others=4):
    """One conversation asked ASKS times, then `others` more that start with the same long prefix and end
    differently - as a parent's sub-agents do - each asked once; then one with a prefix of its own."""
    shared = prefix(seeds(), words)
    tail = lambda name: f"\n\nYou are agent {name} of run {seeds():x}. Reply with the single word OK."
    first = shared + tail("A")
    order = [("A", first)] * ASKS + [(f"other {i + 1}, same prefix", shared + tail(f"B{i}")) for i in range(others)]
    order.append(("own prefix", prefix(seeds(), words) + tail("C")))
    runs = [(name, gw.ask(model, [ask_user(text)])) for name, text in order]
    out = {"runs": [{"name": name, **r} for name, r in runs]}
    times = [seconds(r) for _, r in runs]
    if all(t is not None for t in times):
        cold = min(times[0], times[-1])
        second = times[ASKS:-1]
        warm = hits(second, cold)
        out.update(cold_s=round(statistics.mean([times[0], times[-1]]), 3), other_conversations_s=second,
                   warm=warm, of=others, hit_rate=round(warm / others, 2), reused=warm >= 1)
    return out


TESTS = {"repeat": test_repeat, "grow": test_grow, "lifetime": test_lifetime, "shared": test_shared}


def run(base, key, models, tests, words, gaps, seed=None, sleeper=time.sleep):
    rng = random.Random(seed if seed is not None else int.from_bytes(os.urandom(8), "big"))
    seeds = lambda: rng.getrandbits(48)
    gw = Gateway(base, key)
    results = {"when": time.strftime("%Y-%m-%dT%H:%M:%S"), "prefix_words": words, "warm_ratio": WARM_RATIO,
               "warm_saving_s": WARM_SAVING_S, "models": {}}
    for model in models:
        per = results["models"][model] = {"id": MODELS[model]["id"]}
        for name in tests:
            per[name] = TESTS[name](gw, model, seeds, words, gaps) if name == "lifetime" else TESTS[name](gw, model, seeds, words)
    return results


# --- test 5: what pi itself sent, from cache_log.ts's log -----------------------------------------------

def sprint(rows, cold_s=None):
    """Per model: how far each request extended the one before, and how many of those that did were warm.

    `cold_s` maps a model id to the seconds a cold request of this size takes (from the timing tests);
    without it, the session's own slowest tenth stands in.
    """
    by_model = {}
    for row in rows:
        if row.get("event") == "request":
            by_model.setdefault(row.get("model") or "?", []).append(row)
    out = {}
    for model, requests in by_model.items():
        later = [r for r in requests if r.get("previous_bytes")]
        shares = [r["shared_prefix_bytes"] / r["previous_bytes"] for r in later]
        timed = [r for r in later if r.get("first_event_ms") is not None]
        entry = {"requests": len(requests), "sessions": len({r.get("pid") for r in requests}),
                 "largest_request_bytes": max((r["bytes"] for r in requests), default=0),
                 "extended_the_last": sum(1 for s in shares if s >= 0.99), "compared": len(shares),
                 "least_shared": round(min(shares), 4) if shares else None,
                 "tools_changed": sum(1 for r in later if r.get("tools_same") is False),
                 "not_extensions": [{"n": r["n"], "shared": round(r["shared_prefix_bytes"] / r["previous_bytes"], 4),
                                     "first_difference": r.get("first_difference")} for r in later
                                    if r["shared_prefix_bytes"] / r["previous_bytes"] < 0.99][:10]}
        entry["append_only"] = bool(shares) and entry["extended_the_last"] == entry["compared"] and not entry["tools_changed"]
        if len(timed) >= 4:
            first = [r["first_event_ms"] / 1000 for r in timed]
            cold = (cold_s or {}).get(model) or sorted(first)[-max(1, len(first) // 10)]
            could = [r for r in timed if r["shared_prefix_bytes"] / r["previous_bytes"] >= 0.99]
            warm = [r for r in could if is_warm(r["first_event_ms"] / 1000, cold)]
            entry.update(first_token_s_median=round(statistics.median(first), 3), cold_s=round(cold, 3),
                         could_be_warm=len(could), warm=len(warm),
                         hit_rate=round(len(warm) / len(could), 2) if could else None,
                         warm_s_median=round(statistics.median(r["first_event_ms"] / 1000 for r in warm), 3) if warm else None,
                         seconds_lost_to_misses=round(sum(r["first_event_ms"] / 1000 for r in could if r not in warm)
                                                      - (len(could) - len(warm)) * (statistics.median(r["first_event_ms"] / 1000 for r in warm) if warm else 0), 1),
                         follows_new_bytes_r=correlation([r["bytes"] - r["shared_prefix_bytes"] for r in timed], first),
                         follows_all_bytes_r=correlation([r["bytes"] for r in timed], first))
        out[model] = entry
    return out


def correlation(xs, ys):
    """Pearson's r, or None when either side does not vary."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sx, sy = sum((x - mx) ** 2 for x in xs), sum((y - my) ** 2 for y in ys)
    if sx == 0 or sy == 0:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) ** 0.5, 3)


def main(argv):
    if len(argv) >= 3 and argv[0] == "sprint":
        rows = [json.loads(line) for line in open(argv[1]) if line.strip()]
        cold = {}
        for path in argv[3:]:           # results of the timing tests: what a cold request costs each model
            for per in json.load(open(path))["models"].values():
                if (per.get("repeat") or {}).get("cold_s"):
                    cold[per["id"]] = per["repeat"]["cold_s"]
        json.dump(sprint(rows, cold), open(argv[2], "w"), indent=1)
        return 0
    if len(argv) < 2:
        print(__doc__)
        return 2
    env_file, out_file = argv[0], argv[1]
    options = dict(zip(argv[2::2], argv[3::2]))
    key = next(line.split("=", 1)[1].strip().strip("'\"") for line in open(env_file) if line.startswith("ELM_API_KEY="))
    models = options.get("--models", "qwen,mistral,llama").split(",")
    tests = options.get("--tests", "repeat,grow,lifetime,shared").split(",")
    gaps = [int(g) for g in options.get("--gaps", "10,60,180,420").split(",")]
    results = run(options.get("--base", "https://elm.edina.ac.uk/api/v1"), key, models, tests,
                  int(options.get("--prefix-words", "9000")), gaps)
    json.dump(results, open(out_file, "w"), indent=1)
    for model, per in results["models"].items():
        print(model, {name: (per[name].get("warm"), per[name].get("of"), per[name].get("longest_warm_gap_s")) for name in tests})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
