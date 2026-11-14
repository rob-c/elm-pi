"""Qwen against Mistral on images with known answers, through ELM, as elm-pi sends them.

    python3 vision_eval.py PNG_DIR OUT.jsonl REPS

with the key in the environment as ELM_API_KEY, or ELM_PI_ENV naming an install's .env.

PNG_DIR is what vision_pages.py and its render step make.

Arms: Qwen thinking off (elm-pi's default for Qwen), Mistral thinking high (elm-pi's
default for Mistral), Mistral thinking off. reasoning_effort and sampling are what pi
sends for each (templates/models.json, tests/test_model_requests.py). The key comes from
ELM_API_KEY, or from the .env that ELM_PI_ENV names; it is never printed or written.
"""
import base64
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PNG, OUT, REPS = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
KEY = os.environ.get("ELM_API_KEY") or next(
    l.split("=", 1)[1].strip() for l in Path(os.environ["ELM_PI_ENV"]).read_text().splitlines() if l.startswith("ELM_API_KEY="))
BASE = "https://elm.edina.ac.uk/api/v1"
QWEN, MISTRAL = "Qwen/Qwen3.5-397B-A17B-FP8", "mistralai/Mistral-Small-4-119B-2603"
ARMS = {
    "qwen-off": {"model": QWEN, "reasoning_effort": "none", "temperature": 0.7, "top_p": 0.8, "top_k": 20,
                 "min_p": 0.0, "presence_penalty": 1.5},
    "mistral-high": {"model": MISTRAL, "reasoning_effort": "high", "temperature": 0.7},
    "mistral-off": {"model": MISTRAL, "reasoning_effort": "none", "temperature": 0.15},
}

ASK = ("Look at this image carefully. First describe what it shows in 3 to 6 sentences. Then, as the last thing "
       "in your reply, give one JSON object with exactly these keys: {keys}. Copy text exactly as it appears in "
       "the image; give numbers as numbers.")
COMPARE = ("These two images are two versions of the same {thing}: the first is before a change, the second after. "
           "List every visible difference between them - text, colours, items added or removed, values. Do not list "
           "anything that is the same in both. End your reply with one JSON object: "
           '{{"differences": [{{"where": "...", "before": "...", "after": "..."}}]}}.')
ITEMS = {
    "a1_bars": (["a1_bars"], ASK.format(keys="title (string), bar_count (integer), tallest_bar_label (string), "
                                      "tallest_bar_value (number), red_bar_label (string)")),
    "a2_lines": (["a2_lines"], ASK.format(keys="x_axis_label, y_axis_label, rising_series (the legend name of the "
                                        "line that goes up), rising_series_colour (a colour name), crossing_x "
                                        "(the x value where the two lines cross)")),
    "a3_shapes": (["a3_shapes"], ASK.format(keys="red_circles, blue_squares, green_triangles (each a count)")),
    "a4_table": (["a4_table"], ASK.format(keys="muon_mass (number), heaviest_particle, positive_particle, "
                                        "row_count (data rows, not counting the header)")),
    "a5_frog_index": (["a5_frog_index"], ASK.format(
        keys="site_title, nav_items (list, in order), active_nav_item, stat_values (list of the large figures in "
             "the 'Frog Facts at a Glance' cards), layout_problems (list of any visual or layout defects you can "
             "see, empty if none)")),
    "b1_page_pair": (["b1_before", "b1_after"], COMPARE.format(thing="web page")),
    "b2_chart_pair": (["b2_bars_before", "b2_bars_after"], COMPARE.format(thing="chart")),
    "b3_subtle_pair": (["b3_before", "b3_after"], COMPARE.format(thing="web page")),
    "b4_identical_pair": (["b4_same_a", "b4_same_b"], COMPARE.format(thing="web page")),
}

LOCK = threading.Lock()


def image_part(name):
    data = base64.b64encode((PNG / f"{name}.png").read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}


def call(arm, item, rep):
    images, prompt = ITEMS[item]
    body = {**ARMS[arm], "max_tokens": 12000, "stream": False,
            "messages": [{"role": "user", "content": [*map(image_part, images), {"type": "text", "text": prompt}]}]}
    req = urllib.request.Request(f"{BASE}/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    started, attempt = time.time(), 0
    while True:
        attempt += 1
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                d = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 8:
                time.sleep(2 ** attempt)
                continue
            d = {"error": f"HTTP {e.code}: {e.read()[:300]!r}"}
            break
        except Exception as e:  # noqa: BLE001
            if attempt < 6:
                time.sleep(2 ** attempt)
                continue
            d = {"error": repr(e)[:300]}
            break
    choice = (d.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    row = {"arm": arm, "item": item, "rep": rep, "seconds": round(time.time() - started, 1), "attempts": attempt,
           "finish": choice.get("finish_reason"), "content": msg.get("content") or "",
           "reasoning_chars": len(msg.get("reasoning_content") or msg.get("reasoning") or ""),
           "usage": d.get("usage"), "error": d.get("error")}
    with LOCK, OUT.open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(f"{arm:13} {item:15} rep{rep} {row['seconds']:6.1f}s finish={row['finish']} err={bool(row['error'])}",
          flush=True)


done = set()
if OUT.exists():
    for line in OUT.read_text().splitlines():
        r = json.loads(line)
        if not r.get("error"):
            done.add((r["arm"], r["item"], r["rep"]))
jobs = [(a, i, r) for r in range(REPS) for i in ITEMS for a in ARMS if (a, i, r) not in done]
with ThreadPoolExecutor(3) as pool:
    list(pool.map(lambda j: call(*j), jobs))
