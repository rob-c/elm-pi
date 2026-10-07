---
name: elm-dynamic-workflows
description: "Using the `workflow` tool (pi-dynamic-workflows) on this install: when it may be used, checking a script with workflow-check before running it, getting the result back with background:false, model rules, and recovering a run without relaunching. Load it before any `workflow` tool call. Not for subagent workflow scripts (see elm-subagent-workflows)."
---

# The `workflow` tool (pi-dynamic-workflows)

### The `workflow` tool is installed, and never takes a `model`

`@quintinshaw/pi-dynamic-workflows` provides the `workflow` and
`workflow_control` tools and the commands `/ultracode`, `/effort`,
`/deep-research`, `/adversarial-review`, `/code-review`, `/multi-perspective`,
`/codebase-audit` and `/workflows`. Use it only when the user asks for it; its
keyword trigger is switched off here, and `/ultracode` arms an exhaustive fan-out
for every message until `/ultracode off`. `/deep-research` needs the web: do not
use it unless the session was started with `pi --remote` (otherwise every
request is a 403 from the egress proxy).

Its agents are **not** pi-subagents children: they run in-process, `qwen.md` and
`llama.md` do not apply to them, and they have pi's builtin tools (`read`,
`bash`, `edit`, `write`), not the anchor tools. This install loads the ELM-only
policy, the permission gate, the protected-paths guard and cc-safety-net into
them (`providerMiddlewareExtensions` in the workflow `settings.json`). Tell each
one in its prompt exactly what to return and to keep scratch under `.pi/tmp/`.

**Never pass `model` to `agent()`, and never pass `qwen` or `llama` as a model**
- those are pi-subagents agent names. `inheritMainModel` is on, so an agent with
no `model` runs on the session model. Naming one is how a real run here lost five
agents at once: the script asked for `elm/qwen-3.5-397b`, an id that does not
exist, and every agent came back `404 model_not_found`. If a run genuinely needs
a specific model, the only two are `elm/Qwen/Qwen3.5-397B-A17B-FP8` and
`elm-shim/meta-llama/Llama-3.3-70B-Instruct`, as exact provider/id pairs;
`agent/extensions/workflow-model-scope.ts` refuses anything else before a session
is created.

**Check the script before you run it.** The tool's own error is only a position -
`Unexpected token (111:47)` - and the script was sent as one JSON string, so
there is no line to look at. A real run here failed twice that way on a
`sections.map((section, idx) => () => agent(...))` whose last line closed
`agent(` but not `.map(`. So write the script to `.pi/tmp/<name>.mjs` first and
run `workflow-check .pi/tmp/<name>.mjs` in `bash`: it runs the tool's own parser
and prints the offending lines with a caret. Fix it, check again, and call
`workflow` with exactly the checked text once it prints `ok`. The other
checkers are wrong here: `subagent({ action: "validate" })` refuses `export` by
design, and `node --check` rejects the top-level `return` these scripts end with.

Keep long prompts out of the call: build each one in a top-level `const` (or a
plain function returning a string), then call `agent(prompt)` on one short
line, so every bracket closes where you can see it. Prompt text is a template
literal: a `${...}` in it is interpolated, so LaTeX or other text containing
`${` must be escaped as `\${`, and a literal backtick as `` \` ``.

Every script starts with `export const meta = { name: "...", description: "..." }`
- the opposite of a `subagent` workflow script, which must not have one. Its API
is **not** `subagent`'s: `await agent("...")` returns the
agent's text as a **string** (a validated object with `schema`, or **`null`** if
the agent failed after retries), and `await parallel([...])` returns those values
as an array in input order. There is no `.ok`/`.output`/`.structuredOutput`:

<bad-example>
```js
// WRONG. agent() resolved to a string, so .output is undefined twice.
const [a, b] = await parallel([() => agent("..."), () => agent("...")]);
return { a: a.output, b: b.output };
```
</bad-example>

<good-example>
```js
const [a, b] = await parallel([() => agent("..."), () => agent("...")]);
return { report: `${a}\n\n${b}` };
```
</good-example>

**Get the result in the same reply.** Runs are background by default, and
`bg_wait` does not see them - they are not pi-subagents runs, so it answers
`No active run matched`. When you need the result to finish your answer, which
is always the case in print mode (`pi -p`), pass `background: false`. For a run
that is already in the background, `workflow_control({ action: "status", runId })`
reports its state, and its returned value is in
`~/.pi/workflows/projects/*/runs/<runId>.json.result-*` once it completes.
**Never run a completed workflow again to get its result**; read that file.

The message delivered back shows only a
`report`, `summary`, `verdict` or `synthesis` string field, or a bare string, or
the first 400 characters of the JSON, followed by `Full result: <path>`. So return
`{ report: "<everything the caller needs>", ...details }`, or read that file.

An empty `{}` means the return was wrong; `null` values mean agents failed. The
work is recoverable without relaunching: the returned value is in
`<runId>.json.result-<sha>`, and every agent's text is in
`<runId>.json.events.jsonl` (a delta log; replay it and read `agents[].result`).
They live under `workflows/projects/<project>-<hash>/runs/` in `~/.pi` (package
3.13 and earlier) or in this install's `agent/` directory (3.14 and later).
