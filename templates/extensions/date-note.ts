/**
 * Today's date, as a section of the system prompt.
 *
 * pi's system prompt gives the working directory but not the date, so the model takes the
 * year from its training: in test7 (2026-11-12) the parent's design plan, and so every page's
 * footer, said "© 2024". A sub-agent gets the section too, in its own prompt. It changes once a
 * day, which costs a session running past midnight one uncached request.
 *
 * A section, not a returned `systemPrompt`: a returned prompt is sent instead of the sections,
 * rendered when this handler runs, so every section an extension loaded after this one adds -
 * pinned-instructions, remote-research - never reached the model. The first version did that
 * (test9, 2026-11-12: a `pi --remote` session that never searched the web).
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** "Today's date is Thursday 2026-11-12.", in this machine's time zone. */
export function today(now: Date = new Date()): string {
	const pad = (n: number) => String(n).padStart(2, "0");
	const weekday = now.toLocaleDateString("en-GB", { weekday: "long" });
	return `Today's date is ${weekday} ${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}.`;
}

export default function (pi: ExtensionAPI) {
	pi.on("before_agent_start", (event) => {
		event.systemPromptOptions.sections.date = today();
	});
}
