/**
 * Notebook outputs: the rest of an output a notebook summary cut short.
 *
 * lovely-notebook's `notebook_summary` shows each output's first five lines and then
 * "[N more lines]". In auto20 (2026-11-14, a Bateman decay-chain notebook) the cell
 * that printed each nuclide's peak activity was cut after its second row; the model
 * tried `notebook_read_cell_output` on two markdown cells ("Cell index 5 is not a code
 * cell"), gave up, and its reply gave Bi-214's peak as 23.65 min - a number in no
 * output, where the notebook it had run said 38.32 (38.35 computed independently).
 *
 * So, on the two results that led there:
 *   - a summary with a cut output gets a note: the preview is not the output, which
 *     code cells were cut, and the call that reads one whole;
 *   - "is not a code cell" gets the notebook's code cells, read from the file.
 */
import { readFileSync } from "node:fs";
import { isAbsolute, join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** The text parts of a tool result, joined. */
function textOf(content: unknown): string {
	if (!Array.isArray(content)) return "";
	return content.map((c: any) => (c?.type === "text" ? (c.text ?? "") : "")).join("\n");
}

/** Indices of the code cells whose output preview a summary cut short. */
export function cutOutputs(summary: string): number[] {
	const cut: number[] = [];
	// One <cell ...> ... </cell> block per cell, in order.
	for (const m of summary.matchAll(/<cell\b([^>]*)>([\s\S]*?)<\/cell>/g)) {
		const attrs = m[1];
		if (!/\btype="code"/.test(attrs)) continue;
		const index = /\bindex="(\d+)"/.exec(attrs);
		if (!index) continue;
		const outputs = m[2].split(/<output\b/).slice(1).join("<output");
		if (/\[\d+ more lines\]/.test(outputs)) cut.push(Number(index[1]));
	}
	return cut;
}

/** The 0-based indices of a notebook's code cells, or undefined when it cannot be read. */
export function codeCells(path: string, cwd: string): number[] | undefined {
	try {
		const notebook = JSON.parse(readFileSync(isAbsolute(path) ? path : join(cwd, path), "utf8"));
		if (!Array.isArray(notebook?.cells)) return undefined;
		return notebook.cells.flatMap((cell: any, i: number) => (cell?.cell_type === "code" ? [i] : []));
	} catch {
		return undefined;
	}
}

const list = (numbers: number[]) => numbers.join(", ");

export default function (pi: ExtensionAPI) {
	pi.on("tool_result", async (event: any, ctx: any) => {
		if (event.toolName === "notebook_summary" && !event.isError) {
			const cut = cutOutputs(textOf(event.content));
			if (cut.length === 0) return undefined;
			const note =
				`\nThe output previews of cell${cut.length > 1 ? "s" : ""} ${list(cut)} are cut short ("more lines"): ` +
				`what is not shown is not seen. Read an output whole with notebook_read_cell_output ` +
				`{ path, index: ${cut[0]} } before quoting anything from it.`;
			return { content: [...event.content, { type: "text" as const, text: note }] };
		}
		if (event.toolName === "notebook_read_cell_output" && event.isError && /is not a code cell/.test(textOf(event.content))) {
			const path = event.input?.path;
			const cells = typeof path === "string" ? codeCells(path, ctx?.cwd ?? process.cwd()) : undefined;
			if (!cells) return undefined;
			const note = cells.length
				? `\nThe code cells of ${path} are at index ${list(cells)} (0-based, markdown cells counted).`
				: `\n${path} has no code cells.`;
			return { content: [...event.content, { type: "text" as const, text: note }] };
		}
		return undefined;
	});
}
