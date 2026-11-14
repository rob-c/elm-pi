/**
 * A `workflow` script given by its file, and two mistakes caught before a run starts.
 *
 * test15 (2026-11-13): the model wrote its script to .pi/tmp/dino-website.mjs, `workflow-check`
 * printed ok, and then it typed the whole script again as the call's `script` - 2,600 tokens, most
 * of a minute - and the copy escaped its last template literal (\` and \${) where the file had not:
 * "Expecting Unicode escape sequence \uXXXX (176:11)". It wrote and sent the script twice more. So
 * `script` may be the checked file's path: what runs is what was checked, and the call is one line.
 *
 * The same run's page tasks said "copy sharedStyles verbatim into <style> tag", and no task held
 * `${sharedStyles}`: five agents had the word, not the CSS, and drew five colour schemes. Seven
 * agents and 384k tokens later the parent wrote all five pages itself. A top-level text constant
 * that nothing uses, but a prompt names, is refused before the run.
 *
 * The tool's own syntax error is a position only - "(176:11)" - so the line it points at is added.
 *
 * permission-mode.ts and report-guard.ts read the script too, and pi gives no order between the
 * extensions in one folder, so each of them reads a named file itself (`scriptText` there).
 */
import { existsSync, readFileSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { isAbsolute, join, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** The file a `script` names, when it is a path and not a script: one line ending .mjs or .js. */
export function scriptPath(script: unknown, cwd: string): string | undefined {
	if (typeof script !== "string") return undefined;
	const text = script.trim().replace(/^["'`]+|["'`]+$/g, "");
	if (!text || text.length > 1024 || /[\n;(){}=`]/.test(text) || !/\.m?js$/i.test(text)) return undefined;
	return isAbsolute(text) ? text : resolve(cwd, text);
}

type Parse = (source: string) => any;

let parser: Parse | null | undefined;
/** acorn, from the workflow package that runs the script (and parses it with acorn too). */
function acornParse(): Parse | null {
	if (parser !== undefined) return parser;
	parser = null;
	const homes = [process.env.PI_CODING_AGENT_DIR, join(process.cwd(), "agent")].filter(Boolean) as string[];
	for (const home of homes) {
		try {
			const require = createRequire(join(home, "npm/node_modules/@quintinshaw/pi-dynamic-workflows/package.json"));
			const acorn = require("acorn");
			parser = (source) =>
				acorn.parse(source, {
					ecmaVersion: "latest",
					sourceType: "module",
					allowAwaitOutsideFunction: true,
					allowReturnOutsideFunction: true,
				});
			break;
		} catch {
			// not this one
		}
	}
	return parser;
}

/**
 * A top-level constant holding text that no code uses while a prompt names it: the agents were
 * meant to have that text and were given only its name. The name and the prompt's line, or
 * undefined. A script that does not parse is left to the tool, which says so.
 */
export function namedNotPassed(script: string, parse: Parse | null = acornParse()): { name: string; line: string } | undefined {
	if (!parse) return undefined;
	let ast: any;
	try {
		ast = parse(script);
	} catch {
		return undefined;
	}
	const declared = new Map<string, unknown>();
	for (const statement of ast.body ?? []) {
		const declaration = statement.type === "ExportNamedDeclaration" ? statement.declaration : statement;
		if (declaration?.type !== "VariableDeclaration") continue;
		for (const d of declaration.declarations ?? []) {
			const text = d.init?.type === "TemplateLiteral" || (d.init?.type === "Literal" && typeof d.init.value === "string");
			if (d.id?.type === "Identifier" && text && d.id.name !== "meta") declared.set(d.id.name, d.id);
		}
	}
	if (declared.size === 0) return undefined;
	const used = new Set<string>();
	const texts: string[] = [];
	const walk = (node: any, parent: any, key: string) => {
		if (!node || typeof node.type !== "string") return;
		if (node.type === "Identifier" && declared.get(node.name) !== node) {
			const property = parent?.type === "MemberExpression" && key === "property" && !parent.computed;
			const label = parent?.type === "Property" && key === "key" && !parent.computed && !parent.shorthand;
			if (!property && !label) used.add(node.name);
		}
		if (node.type === "TemplateElement") texts.push(node.value?.cooked ?? node.value?.raw ?? "");
		if (node.type === "Literal" && typeof node.value === "string") texts.push(node.value);
		for (const [k, v] of Object.entries(node)) {
			if (k === "type" || k === "loc") continue;
			if (Array.isArray(v)) for (const child of v) walk(child, node, k);
			else if (v && typeof v === "object") walk(v, node, k);
		}
	};
	walk(ast, null, "");
	for (const name of declared.keys()) {
		if (used.has(name)) continue;
		const word = new RegExp(`(^|[^\\w$])${name.replace(/[$]/g, "\\$")}(?![\\w$])`);
		for (const text of texts) {
			const line = text.split("\n").find((l) => word.test(l));
			if (line) return { name, line: line.trim().slice(0, 160) };
		}
	}
	return undefined;
}

/** The line a "(line:column)" error points at, with a caret under the column. */
export function pointAt(script: string, error: string): string | undefined {
	const m = /\((\d+):(\d+)\)\s*$/.exec(error.trim());
	if (!m) return undefined;
	const lines = script.split("\n");
	const n = Number(m[1]);
	const column = Number(m[2]);
	if (n < 1 || n > lines.length) return undefined;
	const shown = lines[n - 1];
	const from = Math.max(0, column - 100);
	return `Line ${n} of the script:\n${shown.slice(from, from + 200)}\n${" ".repeat(column - from)}^`;
}

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", async (event, ctx) => {
		if (event.toolName !== "workflow") return undefined;
		const input = (event.input ?? {}) as Record<string, unknown>;
		const file = scriptPath(input.script, ctx.cwd);
		if (file) {
			if (!existsSync(file) || !statSync(file).isFile())
				return {
					block: true,
					reason:
						`No file ${String(input.script).trim()}: write the script there, check it with \`workflow-check\`, ` +
						"and pass that path as `script`.",
				};
			input.script = readFileSync(file, "utf8");
		}
		if (typeof input.script !== "string") return undefined;
		const named = namedNotPassed(input.script);
		if (!named) return undefined;
		return {
			block: true,
			reason:
				`Not started: \`${named.name}\` is never used, so no agent gets its text - yet a prompt says ` +
				`"${named.line}". An agent sees only its prompt: put \${${named.name}} in the prompt where the text ` +
				"belongs, check the script again, and call `workflow` again.",
		};
	});

	pi.on("tool_result", async (event) => {
		if (event.toolName !== "workflow" || !event.isError) return undefined;
		const script = (event.input as Record<string, unknown> | undefined)?.script;
		if (typeof script !== "string") return undefined;
		const error = event.content
			.filter((c: any) => c.type === "text")
			.map((c: any) => c.text)
			.join("\n");
		const shown = pointAt(script, error);
		if (!shown) return undefined;
		return {
			content: [
				...event.content,
				{
					type: "text" as const,
					text:
						`\n${shown}\nFix it in the script's file, run \`workflow-check\` on it, and pass the file's path as ` +
						"`script` - it runs as checked, with nothing typed twice.",
				},
			],
		};
	});
}
