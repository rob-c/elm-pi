---
name: elm-subagent-workflows
description: "Fanning out several qwen/llama children - the built-in parallel workflow, or a validated runs.all script when steps depend on each other - and collecting the results."
---

# pi-subagents workflow scripts

### One `subagent` call: the parallel workflow, or a script

For anything beyond a single child, make **one** `subagent` call. When the
children are independent, that call is the built-in `parallel` workflow, with
nothing to write or validate:

```js
subagent({ workflow: "parallel", args: { tasks: [
  { agent: "qwen", task: "..." },
  { agent: "qwen", task: "..." },
] } })
```

When one child needs another's result, write a workflow script instead: put it
in a file under `.pi/tmp/` with `write`, validate it, then launch it. These are
calls to the `subagent` **tool**, not shell commands - there is no `subagent`
program:

```js
subagent({ action: "validate", workflow: "./.pi/tmp/survey.js" })
subagent({ workflow: "./.pi/tmp/survey.js" })
```

A `workflow` value containing `/` is a file path. (The other form is one
```` ```js workflow ```` block in your reply plus `subagent({ workflow: true })`
in the same reply, one block and one such call per reply; the file form lets you
validate and launch in turn.) The `workflowScript` parameter was removed in
pi-subagents 0.74.0 and is rejected.

**Two script dialects are installed, and they do not mix.** A pi-subagents
script (this skill, run by `subagent`) is plain statements with top-level
`await`: no `import`, no `export`, no `meta`, and it ends with `return`. A
pi-dynamic-workflows script (the `workflow` tool, `elm-dynamic-workflows`;
offered unless the session was started with `pi --no-workflows`) must start with
`export const meta = {...}` and uses `agent()`/`parallel()`, not `runs`. Putting
either one's header in the other fails validation. `workflow-check` is the other
dialect's checker: its "`export const meta` ... must be the first statement" on
a `runs` script means you used the wrong checker, not that the script needs a
header.

### A `[workflows mode armed` note, and no `workflow` tool

`/ultracode` and `/effort` arm every message of 16 characters or more that the
user types, whether or not the `workflow` tool is loaded; without it, this
install rewrites the note into one line saying so. Either way, look at your
tool list. Without `workflow`, the note's `agent()`, `parallel()`,
`pipeline()`, judges, reviewers and "big tier" name nothing you have: write no
`export const meta` script and run no `workflow-check`. Real runs here wrote a
correct `runs.all` script, let `workflow-check` talk them into `export const
meta`, launched that through `subagent`, failed, and came back to the first
script 11 to 14 turns later. Map the note instead:

- Independent parts, or "N workers" on N separate things: the `parallel` call
  above, with nothing to write or check.
- N workers on one deliverable: N attempts at that one thing, or N roles
  (build, test, review), then one `qwen` judge or your own synthesis, and one
  result delivered. "A short program" with five workers is one program.
- The note's reviewers and judges: a second, small `parallel` call over the
  results. Its completeness check is your own check against the request.
- A question, a small edit or talk: answer directly; the note allows it.

Say once that `/ultracode` drives the `workflow` tool only in a session started
without `--no-workflows` (and without `PI_ELM_WORKFLOWS=0`), and `/ultracode off`
stops the note.

The script is ordinary JavaScript with top-level `await`: `runs.all([...])` for
parallel fan-out, `runs.run` for a keyed child, `runs.lanes` for staged work.
Children come back as plain JSON with `ok`, `output` and `structuredOutput`, and
the model travels with the agent name:

```js
const [survey, edits] = await runs.all([
  { key: "survey", agent: "qwen",  task: "Read src/api/*.ts and return, per file, the exported names and one line on what each does. Read-only." },
  { key: "fmt",    agent: "qwen",  task: "Step 1: read src/util/date.ts. Step 2: replace the body of formatDate with the version below. Step 3: read it back and report the new body.\n\n<exact code>" },
]);
return { survey: survey.output, edits: edits.output };
```

**The script is an orchestrator, not a program.** Its sandbox has `runs.run`,
`runs.all`, `runs.lanes`, `runs.steer`, `runs.status`, `runs.ref`, `runs.refs`,
`emit`, `console`, frozen `args` and plain JavaScript - and **no filesystem, no
shell, no Pi tools and no host globals**: no `require`, `process`, `fs` or
`import`. No nested `async function`s, async arrows or async methods either; use
top-level `await`. `runs.host` is available only to the package-owned named
resources (`review`, `run-ci`). Reading a file, running a command, editing
anything is a child's job; the script launches, races and aggregates.

**`runs.all` returns an ordered array, not a key map.** A `key` labels the child
in traces and for `runs.steer`; the result is not indexed by it:

<bad-example>
```js
// WRONG. Cannot read runs.all result property 'lifecycle': it resolves to an
// ordered array, not a key map.
const results = await runs.all([
  { key: "lifecycle", agent: "qwen", task: "..." },
  { key: "habitat",   agent: "qwen", task: "..." },
]);
return { lifecycle: results.lifecycle, habitat: results.habitat };
```
</bad-example>

<good-example>
```js
// RIGHT. Destructure in launch order; with many children, index into your own map.
const items = [
  { key: "lifecycle", agent: "qwen", task: "..." },
  { key: "habitat",   agent: "qwen", task: "..." },
];
const settled = await runs.all(items);
const by = {};
items.forEach((item, i) => { by[item.key] = settled[i]; });
return { lifecycle: by.lifecycle.output, habitat: by.habitat.output };
```
</good-example>

Passing a variable rather than an array literal means static validation cannot
count the launches, and it says so ("static validation proved 0 launch(es), so
runtime fan-out enforcement remains authoritative"); the budget is still enforced
at runtime.

**Build task text from quoted strings.** A stray backtick inside a template
literal is a `SyntaxError`, and in the reply-block form a line holding only
```` ``` ```` ends the block. Join lines instead:

<good-example>
````js
const task = [
  "Run this:",
  "```bash",
  "npm test",
  "```",
].join("\n");
return runs.run("test", { agent: "qwen", task });
````
</good-example>

**The commonest failure** is the urge to do the work in the script -
`ReferenceError: require is not defined`. The answer is always a child:

<bad-example>
```js
// WRONG. There is no require, no fs, no process, no import in this sandbox.
const fs = require("fs");
const config = fs.readFileSync("src/config.ts", "utf8");
```
</bad-example>

<good-example>
```js
// RIGHT. The child reads it; the script receives what the child returns.
const [read] = await runs.all([
  { key: "read", agent: "qwen", task: "Read src/config.ts and report its exported names, one per line. Read-only." },
]);
const names = read.output;
```
</good-example>

**Validate every workflow before you launch it. Every one, no exceptions.** It
runs no children and costs one call. Launch only after it returns `"ok": true`;
otherwise fix what its `errors` name and validate again. A script that fails to parse never launched
anything, so `bg_wait` answering `No active run matched "<id>". Nothing to wait
for.` after a failed launch is that, not a lost child.

**A script that throws after its children finished has not lost the work.** The
failure notification lists every child and its run id; do not relaunch them.
Read them back with the `subagent` tool:

```js
subagent({ action: "children.list" })
subagent({ action: "status", id: "<run-id>", view: "transcript", lines: 200 })
```

Read the outputs back, finish the aggregation yourself, and say in the report
that the children succeeded and the script did not.

### Children that build parts of one thing

A real run here asked for "5 workers" to build a small pipe-flow framework.
The parent launched eight children at once, one per file, including the main
module and the demo that call the others. Those two guessed the names they
needed: `calculateCFLTimestep`, `setPressureGradient` and
`calculateWomersleyVelocity` did not exist. The solver child wrote stubs over
two siblings' files. The parent asked one child for an artery blood-flow demo
nobody had mentioned. The parent then spent about 40 turns making the parts
fit. So:

- **A number of workers the user names is the most children at once.** Neither
  the `parallel` workflow nor `runs.all` takes a concurrency setting: launch
  that many, and put the rest in a second `runs.all` after the first.
- **Each task keeps to the user's request.** No domain, feature or file they
  did not ask for: a water-in-a-pipe request does not get an artery demo.
- **One file per child, named in its task, and "write only that file".** A
  dependency it lacks goes in its report, not into a stub of its own.
- **Parts that call each other share an interface, written down first.** Put
  the exact exported names and signatures into every task that makes or uses
  them. Or build the parts that are called first, and give the parts that call
  them the first stage's real exports in a second stage:

```js
const built = await runs.all([
  { key: "physics", agent: "qwen", task: "Write only src/physics.js: ... Report its exports with their signatures." },
  { key: "pipe",    agent: "qwen", task: "Write only src/pipe.js: ... Report its exports with their signatures." },
]);
const [main] = await runs.all([
  { key: "main", agent: "qwen", task: "Write only src/index.js, calling these modules exactly as they export:\n\n" + built.map((b) => b.output).join("\n\n") },
]);
return { parts: built.map((b) => b.output), main: main.output };
```

- **Say how each child checks its file**: run it with a time limit and report
  the exit code, or report "syntax-checked only". Name the interpreter to use,
  the project's environment or `python3`, and that the child installs nothing:
  a missing package goes in its report. Three children here once ran
  `python3 -m venv .venv` and `pip install` into the same `.venv` at once.
- **Check the result yourself before you report.** Run what was built, and say
  per file what it got: ran (with the exit code), imported, or syntax-checked
  only - never "tested" for the last two.

The routing rule, per child: **whoever has to decide gets Qwen.** Llama is not a
default and not faster (measured in `elm-delegation`): use it only when Qwen is
rate-limited or the user asks for Llama, and only when all three hold:

1. the task is fully specified, with nothing left to decide
2. it is confined to one named file, or to no files at all
3. the expected answer is short - a lookup, one edit, a format pass, a command
   and its output

Give a Llama child numbered steps even when the task is trivial: a one-line goal
is what produced "FINISHED" with nothing changed. The `delegate` role is pinned to
Llama in `settings.json`; there is no automatic fallback - if it fails, relaunch
on `qwen` yourself.

Two settings back this up, in `agent/settings.json` under `subagents`:

- `agentOverrides` pins `worker`, `scout`, `reviewer`, `oracle` and
  `researcher` to Qwen and `delegate` to Llama, and disables the commercial-CLI
  agents. There is no fallback chain: `pi-subagents` removed `fallbackModels` in
  0.68.0, and a settings override that still sets it is rejected at load. If Qwen
  is rate-limited, retrying on Llama is a new launch you make deliberately.
- `modelScope` is `enforce: true, strict: true` with `allow: elm/*,
  elm-shim/*, inherit`. The ELM-only policy strips commercial catalogues in the
  parent; this closes the same door for children.
