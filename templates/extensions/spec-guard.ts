/**
 * spec-guard: code to be written from a document has its tests written from that document first, by someone else.
 *
 * Why: the treadmill of 2026-11-16 ran "write the parser FORMAT.md describes" 36 times and it passed
 * its hidden check 26 times. The failures were not one bug: an unterminated quote accepted, blank
 * lines counted as invalid ones, 25:00:00 taken as a time, 1.5e3 left a string. Each session read
 * FORMAT.md once, wrote the parser and checked it with cases of its own - one reading, checking
 * itself. Two guards that acted after the code was written did not change that (12 of 15 each,
 * against 10 of 15 without): sent back to the document sentence by sentence, the session that had
 * read "skipped" as "counted" marked its own reading correct; and a sub-agent asked for tests from
 * the document ran them against the parser, saw them fail, and rewrote them to pass ("parser
 * doesn't recognize e-notation", in a test's own description).
 *
 * So the order is turned round. The first write of a code file, in a run whose request names a
 * document it has read, is refused once with what to do first: a sub-agent that reads only the
 * document and writes test_spec.py, while there is no code for the tests to be bent to. Then the
 * code is written against them, and a disagreement is settled by the sentence.
 * Measured the same day: 14 of 15 and 14 of 15, each run with test_spec.py in place before the
 * parser - for 1.2M tokens a run against 0.3M, and about seven minutes against two.
 *
 * Not in the brief, on purpose: tests of input that breaks a form the document lays out. The two
 * failures of those 30 took such input (a field with no =, a quote never closed), so the brief
 * asked for it, and 30 more runs passed 25: the sub-agent wrote five times the refusal tests
 * (median 30 against 6) and four parsers then refused what the document allows (a bare value
 * with = in it), for 2.0M tokens a run. Asking for refusals gets refusals the document never made.
 *
 * Narrow on purpose: the request must name the document and the run must have read it; once per
 * request and twice per session; never in a sub-agent or workflow child; and not when test_spec.py
 * is already there.
 */
import { existsSync } from "node:fs";
import { basename, join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Files whose contents can be executed, by extension - what "wrote code" means here. */
export const CODE = /\.(?:py|pyi|ts|tsx|js|jsx|mjs|cjs|sh|bash|c|h|cc|cpp|cxx|hpp|rs|go|r|jl|f|f90|f95|java|kt|rb|pl|php|lua)$/i;

/** Documents a request can ask for code to be written from, by extension. */
export const DOCUMENT = /\.(?:md|markdown|txt|rst|adoc|org|tex|pdf|html?|docx?)$/i;

/** The tools that write a file: this install's anchor editor is replace/replace_match/insert. */
export const WRITERS = new Set(["write", "edit", "replace", "replace_match", "insert"]);

/** The most notes one session is sent, whatever its runs do. */
export const MAX_NOTES = 2;

/**
 * The documents among `read` that the request names: by file name, as a whole word, whatever its
 * case. "FORMAT.md" in the request names docs/FORMAT.md; "format" alone does not.
 */
export function named(request: string, read: Iterable<string>): string[] {
	const text = request.toLowerCase();
	const found: string[] = [];
	for (const path of read) {
		const name = basename(path).toLowerCase();
		if (!name || !DOCUMENT.test(name)) continue;
		const at = text.indexOf(name);
		if (at < 0) continue;
		const before = at === 0 ? "" : text[at - 1];
		const after = text[at + name.length] ?? "";
		if (/[a-z0-9_-]/.test(before) || /[a-z0-9_]/.test(after)) continue;
		if (!found.includes(path)) found.push(path);
	}
	return found;
}

/** The file the second reading goes in. */
export const TESTS = "test_spec.py";

export function refusal(documents: string[], file: string): string {
	const docs = documents.map((path) => basename(path)).join(" and ");
	return (
		`Not written yet: ${basename(file)} is to come from ${docs}, and a check you write from your own reading of ` +
		"it can only agree with that reading. Have the tests written first, by someone else, while there is no code " +
		"for them to be bent to. Launch one `subagent` (agent qwen) and give it only this: the path of " +
		`${docs}; the names and signatures the request asks for; and the instruction to read ${docs} and nothing ` +
		`else, and write ${TESTS} with unittest - for every sentence of ${docs} at least one test of exactly what ` +
		"that sentence says, the sentence quoted above it - without running them and without writing any other " +
		`file. When it has finished, write ${basename(file)} and run ${TESTS}. Where a test fails, open ${docs} at ` +
		"the quoted sentence and decide from its words which is wrong, the code or the test; fix that one, and " +
		"report the sentences where the two readings differed."
	);
}

type Call = { toolName?: string; input?: { path?: string } };

export default function (pi: ExtensionAPI) {
	// A sub-agent or workflow child is given a brief, not the user's request.
	const child = Boolean(process.env.PI_SUBAGENT_CHILD);
	/** What the user last asked for: a run started by a notice keeps the request it is working on. */
	let request = "";
	let read = new Set<string>();
	let refused = false;
	let refusals = 0;

	pi.on("input", async (event: any) => {
		if (typeof event?.text === "string" && event.source !== "extension") {
			request = event.text;
			read = new Set();
			refused = false;
		}
		return undefined;
	});
	pi.on("tool_call", async (event, ctx: any) => {
		const call = event as Call;
		const tool = call.toolName ?? "";
		const path = call.input?.path;
		if (typeof path !== "string") return undefined;
		if (tool === "read" && DOCUMENT.test(path)) read.add(path);
		if (child || refused || refusals >= MAX_NOTES) return undefined;
		if (!WRITERS.has(tool) || !CODE.test(path) || basename(path) === TESTS) return undefined;
		const documents = named(request, read);
		if (documents.length === 0) return undefined;
		// The second reading is there already: this write is the code it will be run against.
		if (existsSync(join(ctx?.cwd ?? process.cwd(), TESTS))) return undefined;
		// Once per request: a session that goes on without the tests is not asked again.
		refused = true;
		refusals += 1;
		return { block: true, reason: refusal(documents, path) };
	});
}
