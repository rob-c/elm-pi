# ELM tool-call shim

Gives ELM's **Llama 3.3 70B** (and EuroLLM) OpenAI-compatible tool calling, which
they do not have natively.

## Why it is needed

ELM's vLLM instances for those models were started without
`--enable-auto-tool-choice` / `--tool-call-parser`, so **any** request carrying
`tools` fails:

    400  "auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set

Every tool-choice mode fails - `auto`, `required`, a named function, and omitting
the field. Only `tool_choice: "none"` works. Qwen 3.5 397B is unaffected; it is the
one university-hosted model with a tool-call parser.

## What the shim does

    request   lift `tools` into a system prompt block, strip tools/tool_choice,
              rewrite prior assistant tool_calls and tool-results into plain text
    upstream  call ELM normally (no tools field, so no 400)
    response  parse a JSON function call out of the text, re-emit it as OpenAI
              `tool_calls` with finish_reason="tool_calls"

Models with native tool support pass through **untouched** - verified by the
response id (`chatcmpl-tool-...` from vLLM vs `call_...` minted by the shim).
Streaming is supported: the upstream call is buffered and re-emitted as SSE.

## Run

    ./run.sh          # 127.0.0.1:8811 by default

Environment: `SHIM_PORT`, `ELM_BASE_URL`, `SHIM_MODELS` (comma separated).

## Wire into pi

`agent/models.json` gains a second provider pointing at the shim:

```json
"elm-shim": {
  "baseUrl": "http://127.0.0.1:8811",
  "api": "openai-completions",
  "apiKey": "$ELM_API_KEY",
  "models": [{ "id": "meta-llama/Llama-3.3-70B-Instruct",
               "name": "Llama 3.3 70B (ELM via tool-shim)",
               "contextWindow": 128000, "maxTokens": 16384 }]
}
```

Then `pi --model "elm-shim/meta-llama/Llama-3.3-70B-Instruct"`, or pick it in
`/model`. The shim must be running or the provider fails to connect.

## What works, and what does not

Verified:

| Test | Result |
|---|---|
| Llama + tools, non-streaming | `finish_reason: tool_calls`, correct arguments |
| Llama + tools, streaming | correct SSE with a tool_calls delta |
| Qwen through the shim | untouched passthrough |
| pi: read file, fix bug, write back | **works, 9s** |
| pi: multi-step across several files | **unreliable** |

The single-tool loop is solid. Multi-step agentic work is not, and the limit is the
**model, not the shim**: Llama 3.3 70B drifts off-task, invents commands
(`autopep8`, a `venv`, a script that does not exist), and mixes prose with calls.

Parser robustness fixes made along the way, each verified by unit test:

- `json.loads(..., strict=False)` - Llama emits **literal newlines inside JSON
  strings** rather than `\n` escapes whenever an argument contains code. This was
  the single most common failure.
- Strips any ``` fence, not just ```json - Llama also used ```python.
- Accepts a call followed by trailing prose, via first-balanced-brace scanning.

## Honest recommendation

Use it for cheap, single-step work where Llama's speed helps: one file read, one
grep, a summary, a mechanical edit. **Do not** make it your main coding agent -
Qwen 397B remains the only university-hosted model that is genuinely good at
multi-step tool use.

The real fix is server-side: ask the ELM team to add
`--enable-auto-tool-choice --tool-call-parser llama3_json` to the Llama deployment.
That would give native tool calling with no shim, no prompt overhead, and better
reliability than prompt parsing can achieve.


## Making Llama usable: what actually mattered

Three hypotheses tested against the shim directly. Only one held.

**1. Tool payload size — DISPROVED.** The shim injects every tool schema into the
prompt as text, and a real session now carries ~19 tools. Tested 2 tools vs 19 on the
same request: **3/3 correct tool selection either way**, same latency. Tool count is
not the problem.

**2. Multi-turn continuation — REAL, and fixed.** Given a tool result, Llama would
narrate instead of acting: *"To add one, I would need to modify the function."* The
action never happened. Strengthening the system-prompt instruction did nothing. What
worked was attaching the directive to the **function result itself**, at the end of
the prompt where recency gives it weight:

    FUNCTION RESULT (read):
    <content>

    If the task is not finished, emit the next function call as a single-line JSON
    object NOW. Do not describe the action - perform it.

**3. Sampling temperature — REAL, and the bigger lever.** With the nudge in place the
two-step read->replace loop still only completed about half the time. Emitting a
well-formed call is a parsing task, not a creative one:

| Temperature | 2-step loop completed |
|---|---|
| default | ~50% (1 of 2 trials) |
| **0** | **6 of 6 trials** |

The shim now pins `temperature: 0` on every shimmed request (`SHIM_TEMPERATURE`
overrides). Only requests carrying `tools` are affected.

### The boundary that remains

With anchor editing, the recency nudge and temperature 0 all in place, measured in
real pi runs:

| Task phrasing | Result |
|---|---|
| "Do exactly this: (1) read X, (2) replace..., (3) read Y, (4) replace..." | **both files correct, 9s** |
| "Read each file under src/ and add docstrings" | **claims FINISHED, changes nothing** |

The isolated loop is 6/6, so this is not loop mechanics - it is planning. Llama will
execute a list and will not decompose a goal. Give it numbered steps and exact paths.
