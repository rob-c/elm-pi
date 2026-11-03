/**
 * view-outputs: the model looks at the figures and PDFs it makes, and can look
 * at any it is given.
 *
 * Why: a plot with unlabelled axes, an empty panel, a fit drawn off the data or
 * a legend over the curve is only caught by looking at it, and left to itself
 * the model reports "saved spectrum.pdf" without ever having seen it. pi's
 * `read` attaches PNG/JPEG/GIF/WebP, but cannot show a PDF at all, so a
 * rendered paper, a matplotlib PDF or a LaTeX build was text-only or nothing.
 *
 * Two parts:
 * - After every `bash` call - and every `python` call, pi-python's persistent
 *   kernel - image and PDF files in the working directory (and any absolute
 *   path the command or cell names) written during the call are rendered
 *   and attached to that call's result, with a note to examine them. A PDF
 *   handed to `read` is rendered the same way, in place of what read returned.
 * - A `view` tool renders the pages of a PDF, or an image, on request.
 *
 * Rendering is MuPDF compiled to WebAssembly (npm `mupdf`, a dependency in
 * package.json): no native libraries, nothing to download at run time, the same
 * on macOS and on Linux. Its npm build reads no SVG, EPS/PS or HEIC, so those
 * are first converted to PNG or PDF with whichever command-line tool the
 * machine has (CONVERTERS), into a temporary folder that is removed after;
 * with none, the note names the tools that would do it.
 *
 * ELM costs nothing per token, but the context window is finite: a page at
 * 1600 px is roughly 2-3k tokens, so the limits below keep one command from
 * filling it. The model can always `view` the rest.
 */

import { execFile } from "node:child_process";
import { accessSync, constants, mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, delimiter, dirname, extname, isAbsolute, join, relative, resolve } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

/** Longest side of an attached image, in pixels. */
const MAX_SIDE = 1600;
/** Resolution a PDF page is rendered at before MAX_SIDE applies. */
const PDF_DPI = 150;
/** Pages one `view` call renders; the rest are named for a further call. */
const VIEW_MAX_PAGES = 12;
/** Images attached to one bash result, and pages of any one PDF among them. */
const AUTO_MAX_IMAGES = 8;
const AUTO_PDF_PAGES = 4;
/** Text kept per page alongside the picture, so numbers can be quoted exactly. */
const MAX_PAGE_TEXT = 20_000;
/** A file bigger than this is a dataset or a video, not a figure. */
const MAX_FILE_BYTES = 64 * 1024 * 1024;
/** Bounds on the scan of the working directory after each command. */
const SCAN_MAX_DEPTH = 6;
const SCAN_MAX_ENTRIES = 20_000;
/** Tools whose calls can write figures: the shell, and pi-python's persistent kernel (which returns text only). */
const WATCHED = new Set(["bash", "python"]);
const SKIP_DIRS = new Set(["node_modules", "__pycache__", "venv", "site-packages", "dist-packages"]);

const PASSTHROUGH: Record<string, string> = {
	".png": "image/png",
	".jpg": "image/jpeg",
	".jpeg": "image/jpeg",
	".gif": "image/gif",
	".webp": "image/webp",
};
const RENDERED = new Set([".pdf", ".xps", ".bmp", ".tif", ".tiff", ".pnm", ".ppm", ".pgm", ".pbm"]);
interface Converter {
	tool: string;
	args: (input: string, output: string) => string[];
	to: ".png" | ".pdf";
}
const svg: Converter[] = [
	// Bundled in agent/bin, so the first choice on any host. -z 3: SVG units are
	// points, and a matplotlib figure at 1x is ~460 px wide - too small to read.
	{ tool: "resvg", args: (i, o) => ["-z", "3", i, o], to: ".png" },
	{ tool: "rsvg-convert", args: (i, o) => ["-f", "png", "-o", o, i], to: ".png" },
	{ tool: "inkscape", args: (i, o) => [i, "--export-type=png", `--export-filename=${o}`], to: ".png" },
	{ tool: "magick", args: (i, o) => ["-density", "150", i, o], to: ".png" },
	// macOS Quick Look. It picks the output name itself: <input name>.png in the folder given.
	{ tool: "qlmanage", args: (i, o) => ["-t", "-s", String(MAX_SIDE), "-o", dirname(o), i], to: ".png" },
];
// -dSAFER: a PostScript file is a program, and this one came from wherever the data did.
const postscript: Converter[] = [
	{ tool: "gs", args: (i, o) => ["-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-dEPSCrop", "-sDEVICE=pdfwrite", `-sOutputFile=${o}`, i], to: ".pdf" },
	{ tool: "epstopdf", args: (i, o) => [i, `--outfile=${o}`], to: ".pdf" },
	{ tool: "magick", args: (i, o) => ["-density", "150", i, o], to: ".pdf" },
	// No Ghostscript here: run conda-forge's with pixi (agent/bin), which fetches
	// it once into agent/pixi's cache and installs nothing.
	{ tool: "pixi", args: (i, o) => ["exec", "--spec", "ghostscript", "gs", "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-dEPSCrop", "-sDEVICE=pdfwrite", `-sOutputFile=${o}`, i], to: ".pdf" },
];
const photo: Converter[] = [
	{ tool: "sips", args: (i, o) => ["-s", "format", "png", i, "--out", o], to: ".png" },
	{ tool: "magick", args: (i, o) => [i, o], to: ".png" },
	{ tool: "pixi", args: (i, o) => ["exec", "--spec", "imagemagick", "magick", i, o], to: ".png" },
];
/** Formats MuPDF cannot read: each goes through the first of its tools on PATH that succeeds. */
const CONVERTERS: Record<string, Converter[]> = {
	".svg": svg,
	".svgz": svg,
	".eps": postscript,
	".ps": postscript,
	".heic": photo,
	".heif": photo,
	".avif": photo,
	".psd": photo,
};
// Long enough for pixi's first download of Ghostscript or ImageMagick.
const CONVERT_TIMEOUT_MS = 180_000;

const kind = (path: string) => extname(path).toLowerCase();
const viewable = (path: string) => kind(path) in PASSTHROUGH || RENDERED.has(kind(path)) || kind(path) in CONVERTERS;

function onPath(tool: string): string | undefined {
	for (const dir of (process.env.PATH ?? "").split(delimiter)) {
		if (!dir) continue;
		const candidate = join(dir, tool);
		try {
			accessSync(candidate, constants.X_OK);
			return candidate;
		} catch {
			// not in this one
		}
	}
	return undefined;
}

/** Convert a file MuPDF cannot read into a temporary PNG or PDF; undefined when no tool here can. */
async function convert(path: string): Promise<{ file: string; tool: string; cleanup: () => void } | undefined> {
	const dir = mkdtempSync(join(tmpdir(), "elm-pi-view-"));
	const cleanup = () => rmSync(dir, { recursive: true, force: true });
	for (const converter of CONVERTERS[kind(path)] ?? []) {
		const binary = onPath(converter.tool);
		if (!binary) continue;
		const output = join(dir, `converted${converter.to}`);
		const ok = await new Promise<boolean>((done) => {
			execFile(binary, converter.args(path, output), { timeout: CONVERT_TIMEOUT_MS }, (error) => done(!error));
		});
		const file = converter.tool === "qlmanage" ? join(dir, `${basename(path)}.png`) : output;
		try {
			if (ok && statSync(file).size > 0) return { file, tool: converter.tool, cleanup };
		} catch {
			// it ran but wrote nothing: try the next tool
		}
	}
	cleanup();
	return undefined;
}

function noConverter(path: string): string {
	const tools = [...new Set((CONVERTERS[kind(path)] ?? []).map((c) => c.tool))].join(", ");
	return `no converter for ${kind(path)} on this machine (any of: ${tools}). Save the figure as PNG or PDF instead`;
}

type Content = { type: "text"; text: string } | { type: "image"; data: string; mimeType: string };

// biome-ignore lint/suspicious/noExplicitAny: mupdf is loaded lazily, and only its runtime shape is used
let mupdfModule: Promise<any> | undefined;
function mupdf() {
	// Loaded on first use: the WebAssembly start-up is ~100 ms that a session
	// which never makes a figure should not pay.
	mupdfModule ??= import("mupdf");
	return mupdfModule;
}

const seesImages = (ctx: ExtensionContext | undefined) => Boolean(ctx?.model?.input?.includes("image"));

/** "1-3,7" -> [0,1,2,6], clipped to the document. */
function pageList(spec: string | undefined, count: number): number[] {
	if (!spec?.trim()) return Array.from({ length: count }, (_, i) => i);
	const out = new Set<number>();
	for (const part of spec.split(",")) {
		const [a, b] = part.split("-").map((s) => s.trim());
		const from = a ? Number(a) : 1;
		const to = b === undefined ? from : b ? Number(b) : count;
		if (!Number.isInteger(from) || !Number.isInteger(to)) continue;
		for (let p = Math.max(1, from); p <= Math.min(count, to); p++) out.add(p - 1);
	}
	return [...out].sort((x, y) => x - y);
}

interface Rendered {
	pages: number;
	shown: number[];
	content: Content[];
	/** The tool that converted the file first, if one did. */
	via?: string;
}

/** Render a file to images (and page text), at most `limit` pages of those `spec` selects. */
async function render(path: string, spec: string | undefined, limit: number, withText: boolean): Promise<Rendered> {
	const ext = extname(path).toLowerCase();
	const bytes = readFileSync(path);
	const m = await mupdf();

	const isDocument = ext === ".pdf" || ext === ".xps";
	// A raster's longest side in pixels; MuPDF reads PNG, JPEG, TIFF and BMP but not GIF or WebP.
	let pixels: number | undefined;
	if (!isDocument) {
		try {
			const image = new m.Image(bytes);
			pixels = Math.max(image.getWidth(), image.getHeight());
			image.destroy();
		} catch {
			// GIF/WebP: passed through below, and the gateway scales it
		}
	}
	if (ext in PASSTHROUGH && (pixels === undefined || pixels <= MAX_SIDE)) {
		return { pages: 1, shown: [0], content: [{ type: "image", data: bytes.toString("base64"), mimeType: PASSTHROUGH[ext] }] };
	}

	// The file name tells MuPDF which reader to use.
	const doc = m.Document.openDocument(bytes, path);
	try {
		const pages = doc.countPages();
		const wanted = pageList(spec, pages);
		const shown = wanted.slice(0, limit);
		const content: Content[] = [];
		for (const index of shown) {
			const page = doc.loadPage(index);
			const [x0, y0, x1, y1] = page.getBounds();
			const longest = Math.max(x1 - x0, y1 - y0);
			// A page is in points; a raster's page is its pixels at its own dpi, so
			// scale to its pixel size, never past MAX_SIDE.
			const scale = isDocument
				? Math.min(PDF_DPI / 72, MAX_SIDE / longest)
				: Math.min(pixels ?? MAX_SIDE, MAX_SIDE) / longest;
			const pixmap = page.toPixmap(m.Matrix.scale(scale, scale), m.ColorSpace.DeviceRGB, false, true);
			let data = pixmap.asPNG();
			let mimeType = "image/png";
			if (data.length > 4 * 1024 * 1024) {
				data = pixmap.asJPEG(85);
				mimeType = "image/jpeg";
			}
			if (isDocument) {
				let text = withText ? page.toStructuredText("preserve-whitespace").asText().trim() : "";
				if (text.length > MAX_PAGE_TEXT) text = `${text.slice(0, MAX_PAGE_TEXT)}\n[... page text truncated]`;
				content.push({ type: "text", text: `--- page ${index + 1} of ${pages}${text ? ` - text layer:\n${text}` : " (no text layer)"}` });
			}
			content.push({ type: "image", data: Buffer.from(data).toString("base64"), mimeType });
			pixmap.destroy();
			page.destroy();
		}
		return { pages, shown, content };
	} finally {
		doc.destroy();
	}
}

/** render(), through a converter first for the formats that need one. */
async function show(path: string, spec: string | undefined, limit: number, withText: boolean): Promise<Rendered> {
	if (!(kind(path) in CONVERTERS)) return render(path, spec, limit, withText);
	const converted = await convert(path);
	if (!converted) throw new Error(noConverter(path));
	try {
		return { ...(await render(converted.file, spec, limit, withText)), via: converted.tool };
	} finally {
		converted.cleanup();
	}
}

/** Image and PDF files under `root` changed at or after `since` (ms). */
function changedUnder(root: string, since: number): string[] {
	const found: string[] = [];
	let entries = 0;
	const walk = (dir: string, depth: number) => {
		if (depth > SCAN_MAX_DEPTH || entries > SCAN_MAX_ENTRIES) return;
		let list: import("node:fs").Dirent[];
		try {
			list = readdirSync(dir, { withFileTypes: true });
		} catch {
			return;
		}
		for (const entry of list) {
			if (++entries > SCAN_MAX_ENTRIES) return;
			const path = join(dir, entry.name);
			if (entry.isDirectory()) {
				// Hidden folders are .git, .venv, caches and pi's own state, never a figure.
				if (!entry.name.startsWith(".") && !SKIP_DIRS.has(entry.name)) walk(path, depth + 1);
			} else if (entry.isFile() && viewable(entry.name)) {
				if (recent(path, since)) found.push(path);
			}
		}
	};
	walk(root, 0);
	return found;
}

function recent(path: string, since: number): boolean {
	try {
		const st = statSync(path);
		return st.isFile() && st.mtimeMs >= since && st.size > 0 && st.size <= MAX_FILE_BYTES;
	} catch {
		return false;
	}
}

/** Absolute paths with a figure extension that a command names, e.g. --out /tmp/fit.png. */
function namedPaths(command: string): string[] {
	const out: string[] = [];
	for (const match of command.matchAll(/(?:^|[\s'"=])(\/[^\s'"`;|&<>]+\.(?:pdf|png|jpe?g|gif|webp|tiff?|bmp|svgz?|e?ps|heic|heif|avif|psd))(?=$|[\s'";|&)])/gi)) {
		out.push(match[1]);
	}
	return out;
}

export default function (pi: ExtensionAPI) {
	const started = new Map<string, number>();
	/** path -> mtime last attached, so a file is shown again only when it changes. */
	const shownAt = new Map<string, number>();

	pi.on("tool_call", (event) => {
		// Coarse filesystem timestamps (1 s on some) can put a file written at
		// the very start of the call just before it.
		if (WATCHED.has(event.toolName)) started.set(event.toolCallId, Date.now() - 1500);
	});

	pi.on("tool_result", async (event, ctx) => {
		const cwd = ctx?.cwd ?? process.cwd();

		if (event.toolName === "read") {
			// pi's read rejects a compressed PDF as binary and returns an
			// uncompressed one as PDF source, which is no use either: show it.
			const path = typeof event.input.path === "string" ? resolve(cwd, event.input.path) : "";
			if (!path || !RENDERED.has(kind(path)) || !seesImages(ctx)) return;
			try {
				const result = await render(path, undefined, VIEW_MAX_PAGES, true);
				return { content: [{ type: "text", text: header(path, result, cwd) }, ...result.content], isError: false };
			} catch {
				return;
			}
		}

		if (!WATCHED.has(event.toolName)) return;
		const since = started.get(event.toolCallId);
		started.delete(event.toolCallId);
		if (since === undefined) return;

		// bash's command, or the cells pi-python ran: either may name an absolute path.
		const command =
			typeof event.input.command === "string"
				? event.input.command
				: Array.isArray(event.input.cells)
					? event.input.cells.map((cell: { code?: unknown }) => (typeof cell?.code === "string" ? cell.code : "")).join("\n")
					: "";
		const candidates = new Set(changedUnder(cwd, since));
		for (const path of namedPaths(command)) if (recent(path, since)) candidates.add(path);
		const fresh = [...candidates]
			.filter((path) => {
				const mtime = statSync(path).mtimeMs;
				if (shownAt.get(path) === mtime) return false;
				shownAt.set(path, mtime);
				return true;
			})
			.sort();
		if (fresh.length === 0) return;

		const name = (path: string) => (isAbsolute(path) && path.startsWith(`${cwd}/`) ? relative(cwd, path) : path);

		if (!seesImages(ctx)) {
			const note =
				`[view-outputs] This command wrote ${fresh.map(name).join(", ")}. This model cannot see images: ` +
				"have the qwen sub-agent examine them before reporting on them.";
			return { content: [...event.content, { type: "text", text: note }] };
		}

		const attached: Content[] = [];
		const skipped: string[] = [];
		const lines: string[] = [];
		for (const path of fresh) {
			const room = AUTO_MAX_IMAGES - attached.filter((c) => c.type === "image").length;
			if (room <= 0) {
				skipped.push(name(path));
				continue;
			}
			try {
				const result = await show(path, undefined, Math.min(room, AUTO_PDF_PAGES), true);
				attached.push({ type: "text", text: header(path, result, cwd) }, ...result.content);
				lines.push(
					`${name(path)}${result.pages > 1 ? ` (pages ${result.shown.map((i) => i + 1).join(",")} of ${result.pages})` : ""}` +
						(result.via ? ` (converted with ${result.via})` : ""),
				);
			} catch (error) {
				skipped.push(`${name(path)}: ${String(error).replace(/^Error: /, "").slice(0, 240)}`);
			}
		}

		const note = [
			`[view-outputs] This command wrote ${fresh.length} figure/document file(s).` +
				(lines.length ? ` Attached below: ${lines.join("; ")}.` : ""),
			"Examine every attached image before you report on it or build on it: does it show what was intended; " +
				"are axes labelled with units, ranges and scales sensible, legends and text legible and not overlapping; " +
				"are there empty, clipped or wrong panels; does a fit follow the data. Fix and regenerate what is wrong, " +
				"and describe what each figure shows in your report.",
			skipped.length ? `Not attached here - ${skipped.join("; ")}. Look at what can be shown with the view tool.` : "",
		]
			.filter(Boolean)
			.join("\n");
		return { content: [...event.content, { type: "text", text: note }, ...attached] };
	});

	pi.registerTool({
		name: "view",
		label: "View",
		description:
			"Look at a PDF or an image: renders PDF pages (and XPS, TIFF, BMP) to images you can see, with each page's " +
			`text layer, at most ${VIEW_MAX_PAGES} pages per call - ask for further pages with \`pages\`. ` +
			"Use it on every figure or PDF you produce or are given before you describe it, and on a PDF when its " +
			"layout, figures, tables or equations matter. PNG/JPEG also work with read. SVG, EPS/PS, HEIC and PSD " +
			"are converted first with a command-line tool if the machine has one (resvg, rsvg-convert, " +
			"inkscape, ImageMagick, Ghostscript, epstopdf, sips, qlmanage).",
		parameters: Type.Object({
			path: Type.String({ description: "File to view, relative to the working directory or absolute." }),
			pages: Type.Optional(Type.String({ description: 'PDF pages to render, 1-based, e.g. "1-3,7". Default: from page 1.' })),
			text: Type.Optional(Type.Boolean({ description: "Include each PDF page's text layer (default true)." })),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const cwd = ctx?.cwd ?? process.cwd();
			const path = resolve(cwd, params.path);
			const fail = (message: string) => ({ content: [{ type: "text" as const, text: message }], details: {}, isError: true });
			if (!seesImages(ctx)) return fail("This model cannot see images. Ask the qwen sub-agent to view the file.");
			if (!viewable(path)) return fail(`${params.path}: not an image or PDF. Use read for text files.`);
			let size: number;
			try {
				size = statSync(path).size;
			} catch {
				return fail(`${params.path}: no such file.`);
			}
			if (size > MAX_FILE_BYTES) return fail(`${params.path}: ${Math.round(size / 1e6)} MB is too large to render.`);
			try {
				const result = await show(path, params.pages, VIEW_MAX_PAGES, params.text !== false);
				shownAt.set(path, statSync(path).mtimeMs);
				return { content: [{ type: "text", text: header(path, result, cwd) }, ...result.content], details: {} };
			} catch (error) {
				return fail(`${params.path}: could not be shown: ${String(error).replace(/^Error: /, "").slice(0, 300)}`);
			}
		},
	});
}

function header(path: string, result: Rendered, cwd: string): string {
	const name = (path.startsWith(`${cwd}/`) ? relative(cwd, path) : path) + (result.via ? ` (converted with ${result.via})` : "");
	if (result.pages <= 1) return `${name}:`;
	const shown = result.shown.map((i) => i + 1);
	const range = shown.length ? `${shown.length > 1 ? "pages" : "page"} ${spans(shown)}` : "no pages";
	const last = shown[shown.length - 1];
	const more =
		shown.length && last < result.pages
			? ` - view it with pages "${spans(Array.from({ length: result.pages - last }, (_, i) => last + 1 + i))}" for the rest`
			: "";
	return `${name}: ${result.pages} pages, showing ${range}${more}.`;
}

/** [1,2,3,7] -> "1-3,7", in the syntax `pages` takes: "2,4" must not read as 2-4. */
function spans(pages: number[]): string {
	const parts: string[] = [];
	for (let i = 0; i < pages.length; i++) {
		const from = pages[i];
		while (i + 1 < pages.length && pages[i + 1] === pages[i] + 1) i++;
		parts.push(from === pages[i] ? `${from}` : `${from}-${pages[i]}`);
	}
	return parts.join(",");
}
