"""Benchmark 2 (harder): seeds/<task>/, checks/<task>.py (hidden; exit 0 = pass), solutions/<task>/ (reference
files laid over the seed, to prove each check can pass), tasks.json."""
import json, shutil, sys, textwrap
from pathlib import Path
root = Path(sys.argv[1])
for d in ("seeds", "checks", "solutions"):
    shutil.rmtree(root / d, ignore_errors=True); (root / d).mkdir(parents=True)
def put(kind, task, files):
    for rel, content in files.items():
        p = root / kind / task / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(textwrap.dedent(content).lstrip("\n"))
def check(task, code): (root / "checks" / f"{task}.py").write_text(textwrap.dedent(code).lstrip("\n"))
tasks = []
def task(id, prompt, seeded=True): tasks.append({"id": id, "prompt": prompt, "seed": str(root / "seeds" / id) if seeded else ""})

# 1. A feature across three modules, with rules the README states and the code must keep.
put("seeds", "inventory", {
"README.md": """
    # stockroom

    Tracks lab consumables. `Store` holds items; quantities are whole numbers and never negative.
    Every change goes through `Store` and is appended to the audit log (`store.log`), one dict per change.
    `cli.py` is a thin wrapper: it must not touch `Store.items` directly.
    """,
"stockroom/__init__.py": "from .store import Store, StockError\n",
"stockroom/store.py": """
    class StockError(Exception):
        pass


    class Store:
        def __init__(self):
            self.items = {}     # name -> quantity on the shelf
            self.log = []       # audit trail: {"op": ..., "name": ..., "qty": ...}

        def add(self, name, qty):
            if qty <= 0:
                raise StockError("quantity must be positive")
            self.items[name] = self.items.get(name, 0) + qty
            self.log.append({"op": "add", "name": name, "qty": qty})

        def remove(self, name, qty):
            if qty <= 0:
                raise StockError("quantity must be positive")
            if self.items.get(name, 0) < qty:
                raise StockError(f"only {self.items.get(name, 0)} {name} in stock")
            self.items[name] -= qty
            self.log.append({"op": "remove", "name": name, "qty": qty})

        def available(self, name):
            return self.items.get(name, 0)
    """,
"cli.py": """
    import sys
    from stockroom import Store, StockError


    def run(store, argv):
        \"\"\"Run one command against the store and return what to print.\"\"\"
        cmd, args = argv[0], argv[1:]
        try:
            if cmd == "add":
                store.add(args[0], int(args[1]))
                return f"{args[0]}: {store.available(args[0])}"
            if cmd == "remove":
                store.remove(args[0], int(args[1]))
                return f"{args[0]}: {store.available(args[0])}"
            if cmd == "show":
                return f"{args[0]}: {store.available(args[0])}"
        except StockError as e:
            return f"error: {e}"
        return f"error: unknown command {cmd}"


    if __name__ == "__main__":
        print(run(Store(), sys.argv[1:]))
    """})
task("inventory", "Add reservations to stockroom. Store.reserve(name, qty, who) sets stock aside for a person; Store.release(name, who) gives back whatever that person has reserved of that item; Store.collect(name, who) hands it over, taking it off the shelf. Reserved stock is still on the shelf but not available: available() must not count it, and remove() must not take it. Reserving more than is available is a StockError. Add `reserve <name> <qty> <who>`, `release <name> <who>` and `collect <name> <who>` to cli.py, printing the available quantity the same way the other commands do. Keep to the rules in the README.")
check("inventory", """
    import inspect, cli
    from stockroom import Store, StockError
    s = Store(); s.add("tips", 10)
    s.reserve("tips", 4, "ana"); assert s.available("tips") == 6, s.available("tips")
    assert s.items["tips"] == 10, "reserved stock is still on the shelf"
    s.reserve("tips", 2, "ana"); assert s.available("tips") == 4, "a second reservation by the same person adds"
    s.reserve("tips", 3, "ben"); assert s.available("tips") == 1
    for bad in (lambda: s.reserve("tips", 2, "cy"), lambda: s.remove("tips", 2), lambda: s.reserve("tips", 0, "cy")):
        try: bad(); raise AssertionError("should have been refused")
        except StockError: pass
    s.remove("tips", 1); assert s.available("tips") == 0 and s.items["tips"] == 9
    s.release("tips", "ben"); assert s.available("tips") == 3
    s.collect("tips", "ana"); assert s.items["tips"] == 3 and s.available("tips") == 3, (s.items, s.available("tips"))
    # releasing or collecting with nothing reserved is not specified: an error and a no-op both pass
    ops = [e["op"] for e in s.log]
    for op in ("reserve", "release", "collect"): assert op in ops, f"{op} is not in the audit log"
    assert sum(e["op"] in ("add", "remove", "reserve", "release", "collect") for e in s.log) >= 7, "every change is in the audit log"
    t = Store(); t.add("gloves", 5)
    assert cli.run(t, ["reserve", "gloves", "2", "ana"]) == "gloves: 3"
    assert cli.run(t, ["reserve", "gloves", "9", "ben"]).startswith("error: ")
    assert cli.run(t, ["collect", "gloves", "ana"]) == "gloves: 3"
    assert ".items" not in inspect.getsource(cli), "cli.py must not touch Store.items"
""")
put("solutions", "inventory", {
"stockroom/store.py": """
    class StockError(Exception):
        pass


    class Store:
        def __init__(self):
            self.items = {}
            self.log = []
            self.reserved = {}   # name -> {who: qty}

        def _held(self, name):
            return sum(self.reserved.get(name, {}).values())

        def add(self, name, qty):
            if qty <= 0:
                raise StockError("quantity must be positive")
            self.items[name] = self.items.get(name, 0) + qty
            self.log.append({"op": "add", "name": name, "qty": qty})

        def remove(self, name, qty):
            if qty <= 0:
                raise StockError("quantity must be positive")
            if self.available(name) < qty:
                raise StockError(f"only {self.available(name)} {name} available")
            self.items[name] -= qty
            self.log.append({"op": "remove", "name": name, "qty": qty})

        def available(self, name):
            return self.items.get(name, 0) - self._held(name)

        def reserve(self, name, qty, who):
            if qty <= 0:
                raise StockError("quantity must be positive")
            if self.available(name) < qty:
                raise StockError(f"only {self.available(name)} {name} available")
            held = self.reserved.setdefault(name, {})
            held[who] = held.get(who, 0) + qty
            self.log.append({"op": "reserve", "name": name, "qty": qty, "who": who})

        def _take(self, name, who):
            qty = self.reserved.get(name, {}).pop(who, 0)
            if not qty:
                raise StockError(f"{who} has no {name} reserved")
            return qty

        def release(self, name, who):
            qty = self._take(name, who)
            self.log.append({"op": "release", "name": name, "qty": qty, "who": who})

        def collect(self, name, who):
            qty = self._take(name, who)
            self.items[name] -= qty
            self.log.append({"op": "collect", "name": name, "qty": qty, "who": who})
    """,
"cli.py": """
    import sys
    from stockroom import Store, StockError


    def run(store, argv):
        cmd, args = argv[0], argv[1:]
        try:
            if cmd == "add": store.add(args[0], int(args[1]))
            elif cmd == "remove": store.remove(args[0], int(args[1]))
            elif cmd == "reserve": store.reserve(args[0], int(args[1]), args[2])
            elif cmd == "release": store.release(args[0], args[1])
            elif cmd == "collect": store.collect(args[0], args[1])
            elif cmd != "show": return f"error: unknown command {cmd}"
            return f"{args[0]}: {store.available(args[0])}"
        except StockError as e:
            return f"error: {e}"
    """})

# 2. Passes alone, fails in the suite: state shared through a mutable default, far from where it shows.
put("seeds", "state-leak", {
"pipeline.py": """
    def make_config(overrides=None, base={"threshold": 0.5, "channels": [], "calibrated": False}):
        \"\"\"A run configuration: the defaults with the overrides applied.\"\"\"
        config = base
        if overrides:
            config.update(overrides)
        return config


    def select(events, config):
        \"\"\"Events above threshold, in the configured channels (all channels when none are configured).\"\"\"
        chosen = []
        for e in events:
            if e["energy"] < config["threshold"]:
                continue
            if config["channels"] and e["channel"] not in config["channels"]:
                continue
            chosen.append(e)
        return chosen


    def run(events, overrides=None):
        config = make_config(overrides)
        return select(events, config)
    """,
"test_pipeline.py": """
    from pipeline import run

    EVENTS = [{"energy": 0.2, "channel": 1}, {"energy": 0.7, "channel": 1}, {"energy": 0.9, "channel": 2}]

    def test_high_threshold():
        assert len(run(EVENTS, {"threshold": 0.8})) == 1

    def test_one_channel():
        assert len(run(EVENTS, {"channels": [1]})) == 1

    def test_defaults():
        assert len(run(EVENTS)) == 2
    """})
task("state-leak", "test_defaults passes when I run it on its own (pytest test_pipeline.py::test_defaults) but fails when I run the whole file. Find out why and fix the cause, not the test.")
check("state-leak", """
    import subprocess, sys, random, pipeline
    assert not subprocess.run(["git", "diff", "--name-only", "HEAD", "--", "test_pipeline.py"], capture_output=True, text=True).stdout.strip(), "the test was edited"
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "test_pipeline.py"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-500:]
    a = pipeline.make_config({"channels": [3]}); a["channels"].append(4); a["threshold"] = 9
    b = pipeline.make_config()
    assert b == {"threshold": 0.5, "channels": [], "calibrated": False}, f"one call's config leaks into the next: {b}"
    c = pipeline.make_config(); c["channels"].append(7)
    assert pipeline.make_config()["channels"] == [], "the default list is still shared"
""")
put("solutions", "state-leak", {"pipeline.py": """
    import copy

    DEFAULTS = {"threshold": 0.5, "channels": [], "calibrated": False}


    def make_config(overrides=None, base=None):
        config = copy.deepcopy(DEFAULTS if base is None else base)
        if overrides:
            config.update(copy.deepcopy(overrides))
        return config


    def select(events, config):
        chosen = []
        for e in events:
            if e["energy"] < config["threshold"]:
                continue
            if config["channels"] and e["channel"] not in config["channels"]:
                continue
            chosen.append(e)
        return chosen


    def run(events, overrides=None):
        return select(events, make_config(overrides))
    """})

# 3. Too slow, with the same output required.
put("seeds", "slow-export", {
"export.py": """
    def unique_runs(rows):
        \"\"\"Rows with a (run, lumi) pair not seen before, in first-seen order; rows keep their fields.\"\"\"
        seen = []
        out = []
        for row in rows:
            key = (row["run"], row["lumi"])
            if key not in seen:
                seen.append(key)
                out.append(row)
        return out


    def totals_by_run(rows):
        \"\"\"Sum of 'events' per run over the unique rows, as a list of (run, total) sorted by run.\"\"\"
        runs = []
        for row in unique_runs(rows):
            if row["run"] not in runs:
                runs.append(row["run"])
        result = []
        for run in sorted(runs):
            total = 0
            for row in unique_runs(rows):
                if row["run"] == run:
                    total += row["events"]
            result.append((run, total))
        return result
    """,
"README.md": "# export\n\n`totals_by_run` takes minutes on a night's data (about 200,000 rows, a few hundred runs).\n"})
task("slow-export", "totals_by_run in export.py takes minutes on a night's data, as the README says. Make it fast - a second or two for 200,000 rows - without changing what either function returns.")
check("slow-export", """
    import random, time, export
    rng = random.Random(7)
    def rows(n, runs):
        return [{"run": rng.randrange(runs), "lumi": rng.randrange(900), "events": rng.randrange(50), "i": i} for i in range(n)]
    def slow_unique(rs):
        seen, out = set(), []
        for r in rs:
            k = (r["run"], r["lumi"])
            if k not in seen: seen.add(k); out.append(r)
        return out
    def slow_totals(rs):
        t = {}
        for r in slow_unique(rs): t[r["run"]] = t.get(r["run"], 0) + r["events"]
        return sorted(t.items())
    small = rows(3000, 12)
    assert export.unique_runs(small) == slow_unique(small), "unique_runs changed what it returns"
    assert [tuple(x) for x in export.totals_by_run(small)] == slow_totals(small), "totals_by_run changed what it returns"
    assert export.totals_by_run([]) == []
    big = rows(200000, 300)
    t0 = time.time(); got = export.totals_by_run(big); took = time.time() - t0
    assert [tuple(x) for x in got] == slow_totals(big)
    assert took < 3.0, f"{took:.1f} s for 200,000 rows"
    t0 = time.time(); export.unique_runs(big); assert time.time() - t0 < 3.0, "unique_runs is still slow"
""")
put("solutions", "slow-export", {"export.py": """
    def unique_runs(rows):
        seen = set()
        out = []
        for row in rows:
            key = (row["run"], row["lumi"])
            if key not in seen:
                seen.add(key)
                out.append(row)
        return out


    def totals_by_run(rows):
        totals = {}
        for row in unique_runs(rows):
            totals[row["run"]] = totals.get(row["run"], 0) + row["events"]
        return sorted(totals.items())
    """})

# 4. A numerics trap: the textbook formula cancels catastrophically.
put("seeds", "numerics", {"stats.py": """
    import math


    def spread(values):
        \"\"\"Sample standard deviation of the readings.\"\"\"
        n = len(values)
        total = sum(values)
        squares = sum(v * v for v in values)
        return math.sqrt((squares - total * total / n) / (n - 1))
    """, "example.py": """
    from stats import spread
    # timestamps in ns from the DAQ clock: large numbers, small scatter
    readings = [1_700_000_000_000_000_000 + d for d in (3, 7, 4, 9, 2, 6, 5, 8)]
    print(spread(readings))
    """})
task("numerics", "example.py should print about 2.449, the scatter of those timestamps, but it prints 0.0 or crashes with a math domain error depending on the data. Fix spread() so it is right for readings like these, including when they are floats.")
check("numerics", """
    import math, statistics, stats
    off = [3, 7, 4, 9, 2, 6, 5, 8]
    want = statistics.stdev(off)
    assert abs(stats.spread([1_700_000_000_000_000_000 + d for d in off]) - want) < 1e-6
    assert abs(stats.spread([1e9 + d * 1e-3 for d in off]) - want * 1e-3) < 1e-6, "floats near 1e9 with mm scatter"
    assert abs(stats.spread([float(d) for d in off]) - want) < 1e-12
    assert stats.spread([5.0, 5.0, 5.0]) == 0.0
    assert abs(stats.spread([1e15 + 1, 1e15 + 2, 1e15 + 3]) - 1.0) < 1e-6
""")
put("solutions", "numerics", {"stats.py": """
    import math


    def spread(values):
        n = len(values)
        origin = values[0]                       # exact for ints, and removes the large common part of floats
        shifted = [v - origin for v in values]
        mean = math.fsum(shifted) / n
        return math.sqrt(math.fsum((d - mean) ** 2 for d in shifted) / (n - 1))
    """})

# 5. A race: correct single-threaded, wrong under threads.
put("seeds", "race", {"counter.py": """
    import threading
    import time


    class HitCounter:
        \"\"\"Counts hits per detector; used from several reader threads.\"\"\"

        def __init__(self):
            self.counts = {}

        def hit(self, detector):
            current = self.counts.get(detector, 0)
            time.sleep(0)            # the reader yields here while it decodes the next word
            self.counts[detector] = current + 1

        def total(self):
            return sum(self.counts.values())


    def read_all(counter, detector, n):
        for _ in range(n):
            counter.hit(detector)


    if __name__ == "__main__":
        c = HitCounter()
        threads = [threading.Thread(target=read_all, args=(c, "barrel", 2000)) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        print(c.total(), "of", 8 * 2000)
    """})
task("race", "Running counter.py prints fewer hits than were made (it should print 16000 of 16000) and the number changes from run to run. Fix HitCounter so the count is right with any number of reader threads. Don't remove the yield in hit(): it stands for real work.")
check("race", """
    import inspect, threading, counter
    assert "time.sleep(0)" in inspect.getsource(counter.HitCounter.hit), "the yield was removed"
    for attempt in range(3):
        c = counter.HitCounter()
        ts = [threading.Thread(target=counter.read_all, args=(c, d, 1500)) for d in ("barrel", "barrel", "endcap", "barrel", "endcap", "barrel")]
        for t in ts: t.start()
        for t in ts: t.join()
        assert c.total() == 9000, c.total()
        assert c.counts == {"barrel": 6000, "endcap": 3000}, c.counts
""")
put("solutions", "race", {"counter.py": """
    import threading
    import time


    class HitCounter:
        def __init__(self):
            self.counts = {}
            self._lock = threading.Lock()

        def hit(self, detector):
            with self._lock:
                current = self.counts.get(detector, 0)
                time.sleep(0)
                self.counts[detector] = current + 1

        def total(self):
            with self._lock:
                return sum(self.counts.values())


    def read_all(counter, detector, n):
        for _ in range(n):
            counter.hit(detector)
    """})

# 6. A parser from a written spec, with the awkward cases in the spec rather than in examples.
put("seeds", "log-parser", {"FORMAT.md": """
    # Run-log line format

    One record per line: fields separated by single spaces.

        <time> <level> <key>=<value> <key>=<value> ...

    - `time` is `HH:MM:SS` or `HH:MM:SS.mmm`; return it as seconds since midnight (a float).
    - `level` is one of `DEBUG INFO WARN ERROR`, upper case. Anything else is an invalid line.
    - A value is either bare (no spaces, no quotes) or in double quotes. Inside quotes a space is part of
      the value, `\\"` is a quote and `\\\\` is a backslash.
    - Bare values that are whole numbers are returned as `int`, with a decimal point or exponent as `float`,
      everything else - and every quoted value - as `str`.
    - A key may appear more than once: the last one wins.
    - A line with no key=value pairs is valid: its fields are an empty dict.
    - Blank lines and lines starting with `#` are skipped by `parse_lines`.
    - An invalid line raises `ValueError` from `parse_line`; `parse_lines` skips it and counts it.
    """, "runlog.py": '"""Parser for the run-log format in FORMAT.md."""\n'})
task("log-parser", "Write the parser FORMAT.md describes in runlog.py: parse_line(line) returning (seconds, level, fields), and parse_lines(lines) returning (records, n_invalid) where records is the list of those tuples.")
check("log-parser", r'''
    import runlog as R
    assert R.parse_line("00:00:01 INFO") == (1.0, "INFO", {})
    t, lvl, f = R.parse_line('13:05:09.250 WARN run=4021 gain=1.5e3 note="beam off" who=ana')
    assert abs(t - (13 * 3600 + 5 * 60 + 9.25)) < 1e-9 and lvl == "WARN"
    assert f == {"run": 4021, "gain": 1500.0, "note": "beam off", "who": "ana"}, f
    assert type(f["run"]) is int and type(f["gain"]) is float
    assert R.parse_line(r'01:00:00 ERROR msg="say \"hi\" \\ bye" n="12"')[2] == {"msg": 'say "hi" \\ bye', "n": "12"}
    assert R.parse_line("01:00:00 DEBUG a=1 a=2 b=-3 c=2.50 d=x=y")[2] == {"a": 2, "b": -3, "c": 2.5, "d": "x=y"}
    assert R.parse_line('02:00:00 INFO empty="" k=v')[2] == {"empty": "", "k": "v"}
    for bad in ("25:00:00 INFO a=1", "01:00:00 info a=1", "01:00 INFO", "01:00:00 INFO a", '01:00:00 INFO a="unterminated', "garbage", "01:00:00 NOTE a=1"):
        try: R.parse_line(bad); raise AssertionError(f"accepted an invalid line: {bad!r}")
        except ValueError: pass
    recs, n = R.parse_lines(["# header", "", "00:00:02 INFO a=1", "nonsense", "   ", "00:00:03.500 ERROR", "99:99:99 INFO"])
    assert n == 2 and recs == [(2.0, "INFO", {"a": 1}), (3.5, "ERROR", {})], (recs, n)
''')
put("solutions", "log-parser", {"runlog.py": r'''
    import re

    LEVELS = {"DEBUG", "INFO", "WARN", "ERROR"}
    TIME = re.compile(r"^(\d\d):(\d\d):(\d\d)(\.\d{1,3})?$")
    INT = re.compile(r"^[+-]?\d+$")
    FLOAT = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")


    def _fields(text):
        fields, i, n = {}, 0, len(text)
        while i < n:
            if text[i] == " ":
                i += 1
                continue
            eq = text.find("=", i)
            key = text[i:eq] if eq != -1 else ""
            if eq == -1 or not key or " " in key or '"' in key:
                raise ValueError("expected key=value")
            i = eq + 1
            if i < n and text[i] == '"':
                i += 1
                out = []
                while True:
                    if i >= n:
                        raise ValueError("unterminated quote")
                    ch = text[i]
                    if ch == "\\" and i + 1 < n and text[i + 1] in '"\\':
                        out.append(text[i + 1]); i += 2
                    elif ch == '"':
                        i += 1
                        break
                    else:
                        out.append(ch); i += 1
                if i < n and text[i] != " ":
                    raise ValueError("text after closing quote")
                fields[key] = "".join(out)
            else:
                end = text.find(" ", i)
                end = n if end == -1 else end
                raw = text[i:end]
                if '"' in raw:
                    raise ValueError("quote in bare value")
                fields[key] = int(raw) if INT.match(raw) else float(raw) if FLOAT.match(raw) else raw
                i = end
        return fields


    def parse_line(line):
        parts = line.strip().split(" ", 2)
        if len(parts) < 2:
            raise ValueError("too few fields")
        m = TIME.match(parts[0])
        if not m:
            raise ValueError("bad time")
        h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if h > 23 or mi > 59 or s > 59:
            raise ValueError("bad time")
        if parts[1] not in LEVELS:
            raise ValueError("bad level")
        return (h * 3600 + mi * 60 + s + float(m.group(4) or 0), parts[1], _fields(parts[2] if len(parts) > 2 else ""))


    def parse_lines(lines):
        records, invalid = [], 0
        for line in lines:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                records.append(parse_line(line))
            except ValueError:
                invalid += 1
        return records, invalid
    '''})

# 7. A query that double-counts through a join.
put("seeds", "sql-join", {"report.py": """
    import sqlite3


    def build(db):
        db.executescript('''
            CREATE TABLE runs (id INTEGER PRIMARY KEY, shift TEXT, events INTEGER);
            CREATE TABLE alarms (id INTEGER PRIMARY KEY, run_id INTEGER, kind TEXT);
        ''')


    def events_per_shift(db):
        \"\"\"Total events and number of alarms per shift, as rows (shift, events, alarms), by shift.\"\"\"
        return db.execute('''
            SELECT r.shift, SUM(r.events), COUNT(a.id)
            FROM runs r JOIN alarms a ON a.run_id = r.id
            GROUP BY r.shift ORDER BY r.shift
        ''').fetchall()
    """, "demo.py": """
    import sqlite3
    from report import build, events_per_shift
    db = sqlite3.connect(":memory:")
    build(db)
    db.executemany("INSERT INTO runs VALUES (?, ?, ?)", [(1, "day", 1000), (2, "day", 500), (3, "night", 800)])
    db.executemany("INSERT INTO alarms (run_id, kind) VALUES (?, ?)", [(1, "hv"), (1, "gas"), (1, "hv")])
    print(events_per_shift(db))     # the day shift took 1500 events, the night shift 800
    """})
task("sql-join", "demo.py prints [('day', 3000, 3)] but the day shift took 1500 events with 3 alarms and the night shift took 800 with none. Fix events_per_shift.")
check("sql-join", """
    import sqlite3, report
    db = sqlite3.connect(":memory:"); report.build(db)
    db.executemany("INSERT INTO runs VALUES (?, ?, ?)", [(1, "day", 1000), (2, "day", 500), (3, "night", 800), (4, "swing", 0)])
    db.executemany("INSERT INTO alarms (run_id, kind) VALUES (?, ?)", [(1, "hv"), (1, "gas"), (1, "hv"), (3, "hv"), (2, "gas")])
    got = [tuple(r) for r in report.events_per_shift(db)]
    assert got == [("day", 1500, 4), ("night", 800, 1), ("swing", 0, 0)], got
    empty = sqlite3.connect(":memory:"); report.build(empty)
    assert report.events_per_shift(empty) == []
""")
put("solutions", "sql-join", {"report.py": """
    import sqlite3


    def build(db):
        db.executescript('''
            CREATE TABLE runs (id INTEGER PRIMARY KEY, shift TEXT, events INTEGER);
            CREATE TABLE alarms (id INTEGER PRIMARY KEY, run_id INTEGER, kind TEXT);
        ''')


    def events_per_shift(db):
        return db.execute('''
            SELECT r.shift, SUM(r.events), SUM((SELECT COUNT(*) FROM alarms a WHERE a.run_id = r.id))
            FROM runs r GROUP BY r.shift ORDER BY r.shift
        ''').fetchall()
    """})

# 8. A physics number that needs a numerical solution done with care.
task("drag-range", "A 0.145 kg ball of radius 3.66 cm is thrown at 40 m/s, 35 degrees above the horizontal, from 1.8 m above level ground. Air drag is quadratic with drag coefficient 0.35, air density 1.20 kg/m^3, g = 9.81 m/s^2, no wind or spin. How far downrange does it land, and how long is it in the air? Write the two numbers to answer.json as {\"range_m\": ..., \"time_s\": ...}, each good to 0.1%, and tell me how you know they are that good.", seeded=False)
check("drag-range", """
    import json
    a = json.load(open("answer.json"))
    assert abs(float(a["range_m"]) - REF_RANGE) / REF_RANGE < 2e-3, (a, REF_RANGE)
    assert abs(float(a["time_s"]) - REF_TIME) / REF_TIME < 2e-3, (a, REF_TIME)
""")
(root / "tasks.json").write_text(json.dumps(tasks, indent=1))
print(len(tasks), "tasks")
