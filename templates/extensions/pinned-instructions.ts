/**
 * Pinned instructions: the user's standing instructions for a project, kept out
 * of the conversation so that compaction cannot summarise them away.
 *
 * Why: when a session compacts, pi summarises the conversation, and an
 * instruction the user gave in a chat turn ("use natural units", "run7.csv is
 * the calibrated file", "do not touch analysis/") survives only if the summary
 * happens to keep it. Measured across seven models including Qwen3.6
 * (arXiv 2606.22528, "Governance Decay"), one compaction raised violations of
 * such instructions from 0% to 30% pooled, while the same instruction in the
 * system prompt did not decay at all; re-injecting it after compaction restored
 * 0%. This extension does that: the model records a standing instruction with
 * `pin_instruction`, and every run puts the list back into the system prompt.
 *
 * Stored per project in agent/pinned/<hash of the working directory>.md, mode
 * 600 - inside the install, not the project, so a cloned repository cannot ship
 * its own "pinned instructions". Sub-agents started in the same directory get
 * the same list.
 */

import { createHash } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

/** Enough for a project's conventions; a pin list that grows past this has
 * stopped being standing instructions and become notes. */
const MAX_PINS = 30;
const MAX_PIN_CHARS = 400;

function agentDir(): string {
	return process.env.PI_CODING_AGENT_DIR || join(homedir(), ".pi", "agent");
}

function pinFile(cwd: string): string {
	let real = cwd;
	try {
		real = realpathSync(cwd);
	} catch {
		// a directory that has gone away still has a stable name
	}
	const key = createHash("sha256").update(real).digest("hex").slice(0, 16);
	return join(agentDir(), "pinned", `${key}.md`);
}

function readPins(cwd: string): string[] {
	const file = pinFile(cwd);
	if (!existsSync(file)) return [];
	return readFileSync(file, "utf8")
		.split("\n")
		.filter((line) => line.startsWith("- "))
		.map((line) => line.slice(2).trim())
		.filter(Boolean);
}

function writePins(cwd: string, pins: string[]): void {
	const file = pinFile(cwd);
	mkdirSync(join(agentDir(), "pinned"), { recursive: true, mode: 0o700 });
	const header = `# Pinned instructions for ${cwd}\n\n`;
	writeFileSync(file, header + pins.map((pin) => `- ${pin}\n`).join(""), { mode: 0o600 });
	chmodSync(file, 0o600);
}

function render(pins: string[]): string {
	return [
		"# Pinned instructions",
		"",
		"Standing instructions the user gave for this project. They hold for the whole",
		"session and outrank anything a summary of earlier conversation says:",
		"",
		...pins.map((pin, i) => `${i + 1}. ${pin}`),
	].join("\n");
}

const PinParams = Type.Object({
	instruction: Type.String({
		description:
			"The standing instruction, in the user's own words as far as possible, one sentence. " +
			"Only for instructions meant to hold for the rest of the work.",
	}),
});

const UnpinParams = Type.Object({
	number: Type.Number({ description: "Number of the pinned instruction to remove, as listed." }),
});

function text(message: string) {
	return { content: [{ type: "text" as const, text: message }], details: {} };
}

export default function (pi: ExtensionAPI) {
	pi.on("before_agent_start", (event, ctx) => {
		const pins = readPins(ctx?.cwd ?? process.cwd());
		if (pins.length > 0) {
			event.systemPromptOptions.sections.pinned_instructions = render(pins);
		} else {
			delete event.systemPromptOptions.sections.pinned_instructions;
		}
	});

	pi.registerTool({
		name: "pin_instruction",
		label: "Pin instruction",
		description:
			"Record a standing instruction from the user so it survives context compaction: a convention, " +
			"units, which file or dataset is authoritative, something not to touch, or a decision the user made " +
			"that should hold for the rest of the work in this project. It is shown in the system prompt from " +
			"the next request on. Not for one-off requests, task progress, or your own conclusions.",
		parameters: PinParams,
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const cwd = ctx?.cwd ?? process.cwd();
			const instruction = params.instruction.replace(/\s+/g, " ").trim();
			if (!instruction) return text("Nothing to pin: the instruction is empty.");
			if (instruction.length > MAX_PIN_CHARS) {
				return text(`Not pinned: keep a pin under ${MAX_PIN_CHARS} characters - one sentence.`);
			}
			const pins = readPins(cwd);
			if (pins.includes(instruction)) return text(`Already pinned:\n${render(pins)}`);
			if (pins.length >= MAX_PINS) {
				return text(`Not pinned: ${MAX_PINS} instructions are already pinned. Remove one with unpin_instruction first.\n${render(pins)}`);
			}
			pins.push(instruction);
			writePins(cwd, pins);
			return text(`Pinned.\n${render(pins)}`);
		},
	});

	pi.registerTool({
		name: "unpin_instruction",
		label: "Unpin instruction",
		description:
			"Remove a pinned standing instruction by its number, when the user withdraws or replaces it.",
		parameters: UnpinParams,
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const cwd = ctx?.cwd ?? process.cwd();
			const pins = readPins(cwd);
			const index = Math.trunc(params.number) - 1;
			if (index < 0 || index >= pins.length) {
				return text(`No pinned instruction ${params.number}.${pins.length ? `\n${render(pins)}` : ""}`);
			}
			const [removed] = pins.splice(index, 1);
			writePins(cwd, pins);
			return text(`Removed: ${removed}${pins.length ? `\n${render(pins)}` : "\nNo instructions pinned."}`);
		},
	});
}
