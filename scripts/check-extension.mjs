// Checks one elm-pi extension the way a session would load it, and that the repository knows it.
//
//   scripts/check-extension <name | path/to/extension.ts>
//
// 1. Loads it with pi's own resource loader (the same one scripts/check-extensions.mjs and bootstrap use),
//    alone, in a scratch agent folder, and lists what it registers: tools, commands, flags, shortcuts and
//    the events it handles. A load error, or an extension that registers nothing, fails.
// 2. For a file in this repository's templates/extensions: it is in config/elm-pi.json's
//    requiredExtensions, INSTALL.md has its row in the extension table, and a test names it.
// 3. Runs the consistency tests (docs against code) and every test module that names it.
// 4. Type-checks it with the repository's tsconfig when TypeScript is installed in the checkout.
//
// The wrapper (scripts/check-extension) picks the Node and the pi to load with: this clone's own after
// scripts/dev-setup.sh, else the install the shell runs under.
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const repo = resolve(dirname(new URL(import.meta.url).pathname), "..");
const piRoot = process.env.ELM_PI_PI_ROOT;
const arg = process.argv[2];
const problems = [];
const say = (line) => console.log(line);

if (!arg || arg === "-h" || arg === "--help") {
	say("usage: scripts/check-extension <name | path/to/extension.ts>");
	process.exit(arg ? 0 : 2);
}
const file = /\.[cm]?[jt]s$/.test(arg) ? resolve(arg) : join(repo, "templates/extensions", `${arg}.ts`);
if (!existsSync(file)) {
	say(`check-extension: no file ${relative(process.cwd(), file) || file}`);
	process.exit(2);
}
const name = basename(file);
say(`check-extension: ${relative(repo, file).startsWith("..") ? file : relative(repo, file)}`);
// dev01 (2026-11-13) ran the whole suite before scripts/dev-setup.sh, so the tests that load extensions skipped.
if (!existsSync(join(repo, "agent/settings.json")) || !existsSync(join(repo, "node_modules/@earendil-works/pi-coding-agent")))
	say("  note: this clone is not set up - run scripts/dev-setup.sh first, or the tests that load extensions skip");

// 1. load it, alone
if (!piRoot || !existsSync(join(piRoot, "node_modules/@earendil-works/pi-coding-agent/dist/index.js"))) {
	say("  load: no pi to load with - run scripts/dev-setup.sh in this clone, or run this inside an elm-pi session");
	process.exit(2);
}
const { DefaultResourceLoader } = await import(
	pathToFileURL(join(piRoot, "node_modules/@earendil-works/pi-coding-agent/dist/index.js")).href
);
const scratch = mkdtempSync(join(tmpdir(), "elm-pi-check-extension-"));
let registered = 0;
try {
	const agentDir = join(scratch, "agent");
	const cwd = join(scratch, "project");
	mkdirSync(join(agentDir, "extensions"), { recursive: true });
	mkdirSync(cwd, { recursive: true });
	writeFileSync(join(agentDir, "settings.json"), "{}\n");
	cpSync(file, join(agentDir, "extensions", name));
	const loader = new DefaultResourceLoader({ cwd, agentDir });
	await loader.reload();
	const { extensions = [], errors = [] } = loader.getExtensions();
	for (const { error } of errors) problems.push(`it does not load: ${String(error).split("\n").slice(0, 3).join(" | ")}`);
	const mine = extensions.find((e) => basename(e.path ?? "") === name);
	if (mine) {
		const list = (map) => [...(map?.keys?.() ?? [])];
		const parts = [
			["tools", list(mine.tools)],
			["commands", list(mine.commands).map((c) => `/${c}`)],
			["flags", list(mine.flags).map((f) => `--${f}`)],
			["shortcuts", list(mine.shortcuts)],
			["events", list(mine.handlers)],
		];
		for (const [label, items] of parts) if (items.length) say(`  ${label}: ${items.join(", ")}`);
		registered = parts.reduce((n, [, items]) => n + items.length, 0);
		// What a tool draws in the terminal is never run by a load, a test or `pi -p`: dev02 (2026-11-13) wrote
		// renderCall and renderResult with `new Text(...)` and no import of Text, which only an interactive
		// session would have hit. So each is called once here, with stand-ins, for a name that does not exist.
		const theme = new Proxy({}, { get: () => (...a) => String(a[a.length - 1] ?? "") });
		for (const [toolName, tool] of mine.tools ?? []) {
			const def = tool.definition ?? tool;
			const tries = [
				["renderCall", () => def.renderCall?.({}, theme, {})],
				["renderResult", () => def.renderResult?.({ content: [{ type: "text", text: "" }], details: {} }, {}, theme, {})],
			];
			for (const [what, run] of tries) {
				try {
					run();
				} catch (error) {
					if (error instanceof ReferenceError) problems.push(`${toolName}'s ${what} fails: ${error.message} (an import is missing?)`);
				}
			}
		}
		if (registered === 0) problems.push("it loads but registers nothing: no tool, command, flag, shortcut or event handler");
		else say("  load: ok, with pi's own loader");
	} else if (errors.length === 0) problems.push("pi did not load it (is it a .ts or .js file with a default export?)");
} finally {
	rmSync(scratch, { recursive: true, force: true });
}

// The ELM key: no extension needs it (pi signs every request; a session cannot start without one), and
// dev01 (2026-11-13) wrote an /elm-info that showed its first and last four characters.
const text = readFileSync(file, "utf8");
if (/ELM_API_KEY/.test(text) && name !== "elm-shim.ts")
	problems.push("it reads ELM_API_KEY: no extension needs the key, and none may show, log or keep any part of it");

// 2. the repository knows it
const inRepo = resolve(dirname(file)) === join(repo, "templates/extensions");
const testsNaming = [];
if (inRepo) {
	const config = JSON.parse(readFileSync(join(repo, "config/elm-pi.json"), "utf8"));
	if (!config.requiredExtensions.includes(name))
		problems.push(`config/elm-pi.json: "${name}" is not in requiredExtensions (every extension there is checked at install)`);
	const install = readFileSync(join(repo, "INSTALL.md"), "utf8");
	if (!install.includes(`| \`agent/extensions/${name}\` |`))
		problems.push(`INSTALL.md: no row "| \`agent/extensions/${name}\` | what it does |" in the extension table`);
	for (const t of readdirSync(join(repo, "tests")).filter((f) => /^test_.*\.py$/.test(f)))
		if (readFileSync(join(repo, "tests", t), "utf8").includes(name)) testsNaming.push(t.replace(/\.py$/, ""));
	const own = testsNaming.filter((t) => !["test_docs_match_code", "test_repo_consistency", "test_extensions_generated"].includes(t));
	if (own.length === 0) problems.push(`tests/: no test names ${name} - add one that loads it and checks what it does`);
	else say(`  tests naming it: ${own.join(", ")}`);
}

// 3. the consistency tests, and its own
if (inRepo) {
	const modules = [...new Set(["test_docs_match_code", "test_repo_consistency", ...testsNaming])].map((t) => `tests.${t}`);
	const run = spawnSync("python3", ["-m", "unittest", ...modules], { cwd: repo, encoding: "utf8", env: process.env });
	const tail = (run.stderr || "").trim().split("\n");
	const summary = tail.filter((l) => /^(Ran |OK|FAILED)/.test(l)).join(" ");
	if (run.status === 0) say(`  tests: ${summary}`);
	else {
		const failures = tail.filter((l) => /^(FAIL|ERROR):|Error:|AssertionError/.test(l)).slice(0, 12);
		problems.push(`tests fail (${summary || `exit ${run.status}`}):\n      ${failures.join("\n      ")}`);
	}
}

// 4. types
const tsc = join(repo, "node_modules/typescript/bin/tsc");
if (inRepo && existsSync(tsc)) {
	const run = spawnSync(process.execPath, [tsc, "-p", "tsconfig.json", "--noEmit"], { cwd: repo, encoding: "utf8" });
	const out = run.stdout || "";
	const mine = out.split("\n").filter((l) => l.includes(`extensions/${name}`));
	// A tsc that did not run is not a pass (dev02, 2026-11-13: a missing import passed as "types: ok").
	if (run.status !== 0 && !/error TS\d+/.test(out))
		problems.push(`the type check could not run: ${((run.stderr || run.error?.message || "").trim().split("\n").find((l) => /error/i.test(l)) ?? `tsc exited ${run.status}`).slice(0, 200)}`);
	else if (mine.length) problems.push(`type errors:\n      ${mine.slice(0, 10).join("\n      ")}`);
	else say("  types: ok");
} else if (inRepo) say("  types: not checked (TypeScript is not installed in this checkout; npm install in a --remote session adds it)");

if (problems.length) {
	say(`\n${problems.length} problem${problems.length > 1 ? "s" : ""}:`);
	for (const p of problems) say(`  - ${p}`);
	process.exit(1);
}
say(`\nok: ${name} loads, registers ${registered} thing${registered === 1 ? "" : "s"}${inRepo ? ", and is registered, documented and tested" : ""}`);
