---
name: elm-subagent-workflows
description: "Writing, validating and launching a pi-subagents workflow script - one subagent call that launches several qwen/llama children with runs.all - and recovering when one fails. Load it before any subagent call that uses `workflow`. Not for the separate `workflow` tool (see elm-dynamic-workflows)."
---

# pi-subagents workflow scripts

### Mixing both in one orchestration

For anything beyond a single child, make **one** `subagent` call that runs a
workflow script, and launch the children inside it. Write the script to a file
under `.pi/tmp/` with `write`, validate it, then launch it. These are calls to
the `subagent` **tool**, not shell commands - there is no `subagent` program:

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
script (this section, run by `subagent`) is plain statements with top-level
`await`: no `import`, no `export`, no `meta`, and it ends with `return`. A
pi-dynamic-workflows script (the `workflow` tool, next section) must start with
`export const meta = {...}` and uses `agent()`/`parallel()`, not `runs`. Putting
either one's header in the other fails validation.

The script is ordinary JavaScript with top-level `await`: `runs.all([...])` for
parallel fan-out, `runs.run` for a keyed child, `runs.lanes` for staged work.
Children come back as plain JSON with `ok`, `output` and `structuredOutput`, and
the model travels with the agent name:

```js
const [survey, edits] = await runs.all([
  { key: "survey", agent: "qwen",  task: "Read src/api/*.ts and return, per file, the exported names and one line on what each does. Read-only." },
  { key: "fmt",    agent: "llama", task: "Step 1: read src/util/date.ts. Step 2: replace the body of formatDate with the version below. Step 3: read it back and report the new body.\n\n<exact code>" },
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
return runs.run("test", { agent: "llama", task });
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

The routing rule, per child: **whoever has to decide gets Qwen.** Llama is not a
default: use it only when Qwen is rate-limited or the user asks to save
allocation, and only when all three hold:

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

**This split is not a speed optimisation.** Llama is the slower model here, and a
fan-out split across both is slower end to end than sending all of it to Qwen.
