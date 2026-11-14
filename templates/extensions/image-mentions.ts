/**
 * Image mentions: an image a message names goes to the model with it.
 *
 * pi attaches an image the user pastes (Ctrl+V), drags into a terminal that
 * supports it, or adds with `@`. One named in the text - "what is wrong with
 * figures/fit.png?", the path of a screenshot - reached the model only if the
 * model chose to `read` it, and looking is the step a model skips: in test5 it
 * reported a site "100% visually consistent" without having seen a page. Qwen
 * and Mistral both see images, and on ELM a look costs a few thousand tokens of
 * no budget at all. So the images a message names are attached to it, as a
 * pasted one is, and pi shrinks them on the way in as it does a paste.
 *
 * What counts: a .png, .jpg/.jpeg, .gif or .webp path that exists - relative to
 * the working folder, absolute, or under ~ - written plainly, in quotes or
 * backticks, with spaces escaped (`Screenshot\ 1.png`, as a terminal drop writes
 * it) or not at all (`~/Desktop/Screenshot 2026-11-12 at 10.00.00.png`: the
 * longest run of words ending in the name that is a file wins). Not a path in a
 * hidden folder (~/.ssh, ~/.config): a picture worth showing does not live
 * there. Not one written with `@`, which pi attaches itself - in the editor as
 * `@path`, from the command line as `<file name="/abs/path.png"></file>` in the
 * text, which is skipped too (it was attached twice). At most MAX_IMAGES
 * a message, each at most MAX_BYTES. A sub-agent's task is a message too, so a
 * qwen child given "check plots/fit.png" starts with the plot in front of it. A
 * model that cannot see images (Llama through the shim) gets nothing attached.
 */
import { readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { extname, isAbsolute, join, resolve, sep } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const MAX_IMAGES = 8;
export const MAX_BYTES = 20 * 1024 * 1024;

const MIME: Record<string, string> = {
	".png": "image/png",
	".jpg": "image/jpeg",
	".jpeg": "image/jpeg",
	".gif": "image/gif",
	".webp": "image/webp",
};
/** An image name's end: the extension, then the end, space, closing punctuation or a full stop. */
const NAME_END = /\.(png|jpe?g|gif|webp)(?=$|[\s"'`)\]>,;:!?]|\.(?:\s|$))/gi;
/** How far back a name with unescaped spaces may start. */
const MAX_WORDS = 12;

/** A candidate as written, made a path: quotes and backticks off, escaped spaces unescaped. */
function clean(candidate: string): string {
	return candidate.trim().replace(/^["'`(<[]+/, "").replace(/\\ /g, " ");
}

/** Where a written path points: ~ expanded, relative ones from cwd. */
export function resolvePath(written: string, cwd: string, home: string = homedir()): string {
	if (written === "~" || written.startsWith("~/")) return join(home, written.slice(2));
	return isAbsolute(written) ? written : resolve(cwd, written);
}

/** Inside a hidden folder: any part of the path after the first that starts with a dot. */
function hidden(path: string): boolean {
	return path.split(sep).slice(1, -1).some((part) => part.startsWith(".") && part !== "." && part !== "..");
}

/**
 * The image files a text names, as absolute paths, first mention first. `isFile` says
 * whether a path is an image file worth attaching; it is passed in so a test can stub it.
 */
export function mentionedImages(text: string, cwd: string, isFile: (path: string) => boolean, home: string = homedir()): string[] {
	const found: string[] = [];
	// pi's own attachments (`pi @fit.png -p ...`), already on the message: blanked, same length.
	text = text.replace(/<file name="[^"]*">[\s\S]*?<\/file>/g, (tag) => " ".repeat(tag.length));
	for (const match of text.matchAll(NAME_END)) {
		const end = (match.index ?? 0) + match[0].length;
		// Every place the name could start, from the farthest word back to the nearest:
		// the longest that is a file is the one meant.
		const starts: number[] = [];
		for (let i = end - 1, words = 0; i >= 0 && words <= MAX_WORDS; i--) {
			const ch = text[i];
			const boundary = /[\s"'`(<[]/.test(ch) && text[i - 1] !== "\\";
			if (boundary) {
				starts.push(i + 1);
				if (/\s/.test(ch)) words++;
			}
			if (i === 0) starts.push(0);
		}
		for (const start of starts.reverse()) {
			const written = clean(text.slice(start, end));
			if (!written || written.startsWith("@") || !(extname(written).toLowerCase() in MIME)) continue;
			const path = resolvePath(written, cwd, home);
			if (hidden(path) || !isFile(path)) continue;
			if (!found.includes(path)) found.push(path);
			break;
		}
		if (found.length >= MAX_IMAGES) break;
	}
	return found;
}

/**
 * The MIME type a file's first bytes give it, or undefined. A file named .jpg that is not one -
 * a download that saved the server's error reply - makes the gateway refuse the request with
 * 400 "cannot identify image file", and every later one while it stays in the conversation
 * (test9, 2026-11-12, through view-outputs, which checks the same way).
 */
export function imageType(bytes: Uint8Array): string | undefined {
	const ascii = (from: number, to: number) => String.fromCharCode(...bytes.subarray(from, to));
	if (bytes.length >= 8 && bytes[0] === 0x89 && ascii(1, 4) === "PNG") return "image/png";
	if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "image/jpeg";
	if (bytes.length >= 6 && /^GIF8[79]a$/.test(ascii(0, 6))) return "image/gif";
	if (bytes.length >= 12 && ascii(0, 4) === "RIFF" && ascii(8, 12) === "WEBP") return "image/webp";
	return undefined;
}

function attachable(path: string): boolean {
	try {
		const info = statSync(path);
		return info.isFile() && info.size > 0 && info.size <= MAX_BYTES && imageType(readFileSync(path).subarray(0, 16)) !== undefined;
	} catch {
		return false;
	}
}

export default function (pi: ExtensionAPI) {
	pi.on("input", async (event, ctx) => {
		if (event.source === "extension") return { action: "continue" };
		if (!ctx.model?.input?.includes("image")) return { action: "continue" };
		const paths = mentionedImages(event.text, ctx.cwd ?? process.cwd(), attachable);
		if (paths.length === 0) return { action: "continue" };
		const images = paths.map((path) => {
			const bytes = readFileSync(path);
			return { type: "image" as const, data: bytes.toString("base64"), mimeType: imageType(bytes) ?? MIME[extname(path).toLowerCase()] };
		});
		return { action: "transform", text: event.text, images: [...(event.images ?? []), ...images] };
	});
}
