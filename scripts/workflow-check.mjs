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
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

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

const source = readFileSync(file, "utf8");
try {
  const { meta } = parseWorkflowScript(source);
  console.log(`ok: ${file} parses as a workflow script (meta.name "${meta.name}")`);
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
