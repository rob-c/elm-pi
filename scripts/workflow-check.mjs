// Checks a pi-dynamic-workflows script with the package's own parser, before it
// is sent to the `workflow` tool.
//
// The tool reports a syntax error only as a position - "Unexpected token
// (111:47)" - in a script the model sent as one JSON string, so it has no line
// to look at and tends to resend the same mistake. `node --check` is not a
// substitute: these scripts end with a top-level `return`, which the package
// allows and an ES module does not, so node rejects every valid script. This
// calls the exact function the tool uses (parseWorkflowScript: acorn with
// top-level await and return, the determinism blocklist, the meta rules) and
// prints the offending line under the error.
//
//   workflow-check .pi/tmp/<name>.mjs
//
// Two more checks the parser does not make, both from real runs here:
//  - a pi-subagents script (runs.all, no export) is the other dialect. The
//    parser's "export const meta ... must be the first statement" read as an
//    instruction, and the model rewrote a correct script into the wrong one.
//  - the tool runs the body inside `(async () => { ... })()`, so an
//    `export default async function run()` that parses as a module fails only
//    when run. The body is compiled that way here, and not run.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import vm from "node:vm";

const file = process.argv[2];
if (!file) {
  console.error("usage: workflow-check <script.mjs>");
  process.exit(2);
}
const root = process.env.ELM_PI_INSTALL_DIR;
const entry = join(root, "agent/npm/node_modules/@quintinshaw/pi-dynamic-workflows/dist/workflow.js");
let parseWorkflowScript;
try {
  ({ parseWorkflowScript } = await import(pathToFileURL(entry).href));
} catch (error) {
  console.error(`workflow-check: cannot load pi-dynamic-workflows (${error.message})`);
  process.exit(2);
}

let source;
try {
  source = readFileSync(file, "utf8");
} catch (error) {
  console.error(`workflow-check: cannot read ${file} (${error.code ?? error.message})`);
  process.exit(2);
}
if (!/^\s*export\b/m.test(source) && /\bruns\.(all|run|lanes)\s*\(/.test(source)) {
  console.error(`${file}: this is a pi-subagents script (runs.*, no export), not a workflow-tool script.`);
  console.error(`check it with subagent({ action: "validate", workflow: "./${file.replace(/^\.\//, "")}" }) and launch it`);
  console.error("with subagent; do not add `export const meta`. workflow-check is for the `workflow` tool only.");
  process.exit(1);
}
try {
  const { meta, body } = parseWorkflowScript(source);
  try {
    new vm.Script(`(async () => {\n${body}\n})()`, { filename: file });
  } catch (error) {
    console.error(`${file}: parses, but the workflow tool would reject it when it runs: ${error.message}`);
    console.error("hint: the script is top-level statements ending in `return`, run inside an async function -");
    console.error("      no `export default`, no `function run()`, no `import`, and nothing exported but meta");
    process.exit(1);
  }
  console.log(`ok: ${file} parses as a script for the \`workflow\` tool (meta.name "${meta.name}")`);
  // test15: the model typed the checked script out again as `script`, and the copy did not parse.
  console.log(`Run it with workflow({ script: "${file}" }) - the path, not the text: the file runs as checked.`);
} catch (error) {
  const loc = error.loc ?? error.cause?.loc;
  console.error(`${file}${loc ? `:${loc.line}:${loc.column + 1}` : ""}: ${error.message}`);
  if (loc) {
    const lines = source.split("\n");
    for (let n = Math.max(1, loc.line - 2); n <= loc.line; n++) {
      console.error(`${String(n).padStart(5)} | ${lines[n - 1]}`);
    }
    console.error(`${" ".repeat(8 + loc.column)}^`);
    if (/^Unexpected token/.test(error.message)) {
      console.error("hint: an unexpected ) ; or } is usually a bracket opened earlier and never");
      console.error("      closed - count the brackets of the call this line ends, e.g. map((x) => agent(...))");
    }
  }
  process.exit(1);
}
