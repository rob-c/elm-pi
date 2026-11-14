---
name: elm-dynamic-workflows
description: "The `workflow` tool (offered unless pi --no-workflows) - when to use it, checking a script with workflow-check, getting results back. Read before any workflow call."
---

# The `workflow` tool (pi-dynamic-workflows)

If a `workflow` call sent you here, you have the tool: read this, then make the
call again. Only a `[workflows mode armed` note in a session with no `workflow`
tool is handled elsewhere, in `elm-subagent-workflows`. (A live run on
2026-11-13 read "not in your tool list? then this does not apply" right after
its own `workflow` call and told the user the tool was missing.)

### The `workflow` tool is installed, and never takes a `model`

`@quintinshaw/pi-dynamic-workflows` provides the `workflow` and
`workflow_control` tools and the commands `/ultracode`, `/effort`,
`/deep-research`, `/adversarial-review`, `/code-review`, `/multi-perspective`,
`/codebase-audit` and `/workflows`. The two tools are offered in every session
except one started with `pi --no-workflows` or `PI_ELM_WORKFLOWS=0`; asked for a
workflow there, say that it needs a session started without that. Use it for
staged work that reads and judges - find, then verify each finding; several
independent attempts, then a judge - where one `parallel` fan-out is too flat.
A fan-out that writes files is `subagent`'s: its children are each given their
own files, refused a sibling's, and you are told who wrote what. A workflow
agent is only refused replacing, unread, a file another changed after it
started; give each one its own files to write. Its keyword
trigger stays switched off here, and `/ultracode`, which from then on arms
every message of 16 characters or more that does not start with `/`, until
`/ultracode off`, is the user's to type. `/deep-research` needs the web: do not
use it unless the session was started with `pi --remote` (otherwise every
request is a 403 from the egress proxy).

Its agents are **not** pi-subagents children: they run in-process, `qwen.md` and
`llama.md` do not apply to them, and they have pi's builtin tools (`read`,
`bash`, `edit`, `write`, and `view`), not the anchor tools. This install loads the
ELM-only policy, the permission gate, the protected-paths guard, cc-safety-net,
command-guard and the per-session guards (report, server and claim checks, the
date) into them (`providerMiddlewareExtensions` in the workflow `settings.json`).
Of the ownership guard they get one rule: an agent may not replace, unread, a
file another changed after it started. Nothing else keeps parallel agents apart,
so give each its own files to write. They cannot ask the user
anything: what the permission gate would ask about is refused, so in `manual`
and `read-only-auto` mode they can only read, and a script that asks them to write or run something
is refused before it starts - use `subagent` there. Tell each one in its prompt exactly what to return and
to keep scratch under `.pi/tmp/`.

**Never pass `model` to `agent()`, and never pass `qwen` or `llama` as a model**
- those are pi-subagents agent names. `inheritMainModel` is on, so an agent with
no `model` runs on the session model. Naming one is how a real run here lost five
agents at once: the script asked for `elm/qwen-3.5-397b`, an id that does not
exist, and every agent came back `404 model_not_found`. If a run genuinely needs
a specific model, the only three are `elm/@QWEN_MODEL@`, `elm/@MISTRAL_MODEL@`
and `elm-shim/@LLAMA_MODEL@`, as exact provider/id pairs;
`agent/extensions/workflow-model-scope.ts` refuses anything else before a session
is created.

**Check the script before you run it.** The tool's own error is only a position -
`Unexpected token (111:47)` - and the script was sent as one JSON string, so
there is no line to look at. A real run here failed twice that way on a
`sections.map((section, idx) => () => agent(...))` whose last line closed
`agent(` but not `.map(`. So write the script to `.pi/tmp/<name>.mjs` first and
run `workflow-check .pi/tmp/<name>.mjs` in `bash`: it runs the tool's own parser
and prints the offending lines with a caret. Fix it, check again, and once it
prints `ok` call `workflow({ script: ".pi/tmp/<name>.mjs" })` - the path, not the
text: elm-pi runs the checked file. test15 (2026-11-13) typed a checked script out
again instead, and the copy escaped a template literal the file had not. The other
checkers are wrong here: `subagent({ action: "validate" })` refuses `export` by
design, and `node --check` rejects the top-level `return` these scripts end with.

Keep long prompts out of the call: build each one in a top-level `const` (or a
plain function returning a string), then call `agent(prompt)` on one short
line, so every bracket closes where you can see it. Prompt text is a template
literal: a `${...}` in it is interpolated, so LaTeX or other text containing
`${` must be escaped as `\${`, and a literal backtick as `` \` ``.

**An agent gets only its prompt.** Text an agent needs - a stylesheet, a page
template, a list of facts - reaches it only as `${name}` inside its prompt; a
prompt that says "copy sharedStyles verbatim" gives it the word. test15's five
page agents got exactly that and drew five colour schemes, so a script whose
prompts name a text constant that nothing uses is not started. And the files the
user asked for go where they will look - the launch directory - not `.pi/tmp/`,
which is for the script itself and other scratch.

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

A complete script, three attempts at one thing and a judge:

<good-example>
```js
export const meta = { name: "weighted_mean_attempts", description: "Three attempts at one module, one judge",
  phases: [{ title: "Build" }, { title: "Judge" }] };

const build = (n) => `Write only .pi/tmp/attempt${n}/stats.py: a weighted mean and its uncertainty, with doctests. Run "timeout 60 python3 -m doctest -v" on it and report the command, its exit code and the file.`;
const attempts = await parallel([1, 2, 3].map((n) => () => agent(build(n), { label: `attempt ${n}`, phase: "Build" })));
const judge = `Pick the attempt that best does what was asked and say why, quoting its exit code.\n\n${attempts.join("\n\n---\n\n")}`;
const verdict = await agent(judge, { label: "judge", phase: "Judge" });
return { report: verdict };
```
</good-example>

Top-level statements only, ending in `return`. `meta` is the first statement, a
plain literal with a short snake_case `name`; `phases` is `[{ title }]`, not
strings; `parallel` takes functions - `() => agent(...)` - not promises or
`{ agent, task }` objects. No `export default`, no `function run()`, no
`import`: real runs here wrote all three. Call `workflow({ script, background:
false })` when you need the result to finish this reply.

**Get the result in the same reply.** Runs are background by default, and
`bg_wait` does not see them - they are not pi-subagents runs, so it answers
`No active run matched`. When you need the result to finish your answer, which
is always the case in print mode (`pi -p`), pass `background: false`. For a run
that is already in the background, `workflow_control({ action: "status", runId })`
reports its state, and its returned value is in
`$PI_CODING_AGENT_DIR/workflows/projects/*/runs/<runId>.json.result-*` once it completes.
**Never run a completed workflow again to get its result**; read that file.

The message delivered back shows only a
`report`, `summary`, `verdict` or `synthesis` string field, or a bare string, or
the first 400 characters of the JSON, followed by `Full result: <path>`. So return
`{ report: "<everything the caller needs>", ...details }`, or read that file.

**`/ultracode` and `/effort` here.** With effort on, every armed message carries
`Effort: ULTRA` (or `HIGH`): fan out widely, more reviewers and judges, a high
`maxAgents`, the big tier. On ELM:

- No model tiers are configured, so `tier: "big"` runs on the session model
  with a one-time warning: leave it out.
- Size the run to the request: one agent per real part, two reviewers for
  `verify`, a judge only over competing attempts, and `maxAgents` set to the
  count you planned (the default is 1000).
- Leave `concurrency` at its default of 8, under the 12 measured for this
  gateway in `elm-delegation`.
- A 429 that outlasts pi's own retries (about 17 minutes of them) pauses the
  whole run, and the automatic resume waits about 5 minutes, doubling each time.
- `verify`, `judgePanel` and `completenessCheck` need each agent to answer
  through the structured-output tool, and one that never does can fail the
  whole run, not one vote: use them sparingly.
- A question, a small edit or talk gets a direct answer; the note allows it.

An empty `{}` means the return was wrong; `null` values mean agents failed. The
work is recoverable without relaunching: the returned value is in
`<runId>.json.result-<sha>`, and every agent's text is in
`<runId>.json.events.jsonl` (a delta log; replay it and read `agents[].result`).
They live under `workflows/projects/<project>-<hash>/runs/` in `~/.pi` (package
3.13 and earlier) or in this install's `agent/` directory (3.14 and later).
