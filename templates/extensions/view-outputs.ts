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
import { accessSync, constants, existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { basename, delimiter, dirname, extname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

/** Files one `view` call shows together for comparing. */
const VIEW_MAX_FILES = 6;
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
	/** Where it lives when it is not on PATH: a macOS app bundle. */
	paths?: string[];
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
// A web page as a browser draws it, for comparing pages by eye: asked to "check the visual
// renderings between each subpage", a real run here got "not an image or PDF" from `view`,
// tried a web server, and reported the pages consistent from grep alone. Headless Chrome or
// Chromium in a throwaway profile, so a running browser's is never touched; its requests go
// through the launcher's egress proxy (HTTPS_PROXY), or with none, no host but this one
// resolves - a rendering reaches no further than the session may. macOS Quick Look as the
// fallback: WebKit, without scripts.
// Chrome also calls Google on its own - updates, sign-in, safe browsing, field trials: every
// render in test8 (2026-11-12) asked the egress proxy for accounts.google.com, clients2.google.com,
// update.googleapis.com and four more, and under `pi --remote` test9's went through. Puppeteer's
// switches (--disable-background-networking and the rest) stopped one call in eleven here, so the
// proxy is given as a PAC script instead, which sends those hosts to a closed port and everything
// else to the egress proxy. Chrome does not fall back to a direct connection when that port
// refuses (checked with the hosts mapped to a local listener: nothing arrived). A host the page
// itself draws from - a Google map, say - is not sent away.
export const CHROME_HOME = [
	"accounts.google.com", "clients1.google.com", "clients2.google.com", "www.google.com", "www.gstatic.com",
	"clientservices.googleapis.com", "update.googleapis.com", "safebrowsing.googleapis.com",
	"optimizationguide-pa.googleapis.com", "content-autofill.googleapis.com",
];

/** The PAC script, as a data: URL, that sends Chrome's own calls nowhere and the page's to `proxy`. */
export function proxyPac(proxy: string, pageHosts: Iterable<string> = []): string {
	const page = new Set([...pageHosts].map((h) => h.toLowerCase()));
	const home = CHROME_HOME.filter((h) => !page.has(h));
	const to = proxy.replace(/^[a-z]+:\/\//i, "").replace(/\/.*$/, "");
	const script =
		`function FindProxyForURL(url, host) { var home = ${JSON.stringify(home)}; ` +
		`for (var i = 0; i < home.length; i++) if (host === home[i]) return "PROXY 127.0.0.1:9"; return "PROXY ${to}"; }`;
	return `data:application/x-ns-proxy-autoconfig;base64,${Buffer.from(script).toString("base64")}`;
}

const pageHosts = (file: string): string[] => {
	try {
		return [...pageResources(file).remote.keys()];
	} catch {
		return [];
	}
};
const browser = (i: string, o: string) => [
	"--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
	`--user-data-dir=${join(dirname(o), "profile")}`, "--window-size=1280,1600", `--screenshot=${o}`,
	...(process.env.HTTPS_PROXY
		? [`--proxy-pac-url=${proxyPac(process.env.HTTPS_PROXY, pageHosts(i))}`]
		: ["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1"]),
	pathToFileURL(i).href,
];
const page: Converter[] = [
	{ tool: "google-chrome", paths: ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"], args: browser, to: ".png" },
	{ tool: "chromium", paths: ["/Applications/Chromium.app/Contents/MacOS/Chromium"], args: browser, to: ".png" },
	{ tool: "chromium-browser", args: browser, to: ".png" },
	{ tool: "qlmanage", args: (i, o) => ["-t", "-s", String(MAX_SIDE), "-o", dirname(o), i], to: ".png" },
];
/** Formats MuPDF cannot read: each goes through the first of its tools on PATH that succeeds. */
const CONVERTERS: Record<string, Converter[]> = {
	".html": page,
	".htm": page,
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
const kindOf = kind;
const viewable = (path: string) => kind(path) in PASSTHROUGH || RENDERED.has(kind(path)) || kind(path) in CONVERTERS;
/** Shown by `view` when asked, never attached because a command wrote one: a site generator,
 * a coverage report or nbconvert writes pages by the dozen, each a browser start. */
const ON_REQUEST = new Set([".html", ".htm"]);
const figure = (path: string) => viewable(path) && !ON_REQUEST.has(kind(path));

function executable(path: string): boolean {
	try {
		accessSync(path, constants.X_OK);
		return true;
	} catch {
		return false;
	}
}

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
		const binary = onPath(converter.tool) ?? converter.paths?.find(executable);
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

// A file named .jpg is not always a picture. test9 (2026-11-12) fetched seven "photos" with
// `curl -sL`; each got the server's 16-byte reply "error code: 522", and attaching them as
// JPEGs made the gateway answer 400 "cannot identify image file" - that request and, with the
// files still in the conversation, every one after it. So an image is attached only when its
// first bytes say it is one, and a PNG or JPEG only when it is whole; anything else is reported
// for what it holds. A `context` handler keeps any image whose bytes are not one out of every
// request too, so a session that already holds one recovers.
/** The MIME type a file's first bytes give it, among the formats the gateway reads; else undefined. */
export function imageType(bytes: Uint8Array): string | undefined {
	const ascii = (from: number, to: number) => String.fromCharCode(...bytes.subarray(from, to));
	if (bytes.length >= 8 && bytes[0] === 0x89 && ascii(1, 4) === "PNG") return "image/png";
	if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "image/jpeg";
	if (bytes.length >= 6 && /^GIF8[79]a$/.test(ascii(0, 6))) return "image/gif";
	if (bytes.length >= 12 && ascii(0, 4) === "RIFF" && ascii(8, 12) === "WEBP") return "image/webp";
	return undefined;
}

/** Whether a PNG or JPEG stops before its end marker: an interrupted download. */
export function cutShort(bytes: Uint8Array, type: string): boolean {
	const tail = Buffer.from(bytes.subarray(Math.max(0, bytes.length - 1024)));
	if (type === "image/png") return !tail.includes("IEND");
	if (type === "image/jpeg") return !tail.includes(Buffer.from([0xff, 0xd9]));
	return false;
}

/** What a file that is not an image holds, as "it ...". */
export function whatItHolds(bytes: Uint8Array): string {
	if (bytes.length === 0) return "is empty";
	const head = Buffer.from(bytes.subarray(0, 2048));
	const control = [...head.subarray(0, 512)].filter((b) => b < 9 || (b > 13 && b < 32)).length;
	if (control > 2) return `holds ${bytes.length} bytes that are not PNG, JPEG, GIF or WebP`;
	const text = head.toString("utf8");
	// test13 (2026-11-13): placeholder drawings written as SVG into .jpg files. A browser goes by
	// the name for a local file and shows each as broken; the model called the page "rendering
	// correctly" over seven of them.
	if (/^\s*(?:<\?xml[^>]*>\s*)?(?:<!--[\s\S]*?-->\s*)?<svg\b/i.test(text))
		return `holds an SVG drawing (${bytes.length} bytes) under another picture format's name: a browser shows it as broken - name it .svg`;
	if (/<(?:!doctype\s+html|html|head|body)\b/i.test(text)) {
		const title = /<title[^>]*>([^<]{1,80})/i.exec(text)?.[1].trim();
		return `holds a web page${title ? ` titled "${title}"` : ""} (${bytes.length} bytes)${pageSays(bytes, title)}`;
	}
	const first = text.trim().split("\n")[0].slice(0, 100);
	return `holds ${bytes.length} bytes of text: "${first}"`;
}

/**
 * What an error page says, as `, saying "..."`, or "". test12 (2026-11-13) saved Wikimedia's
 * error page as .jpg five times; the note said only its title, "Wikimedia Error", and the model
 * blamed the egress proxy. The page itself said "Error: 400, Use thumbnail sizes listed on
 * https://w.wiki/GHai". A stated "Error: NNN, reason" is preferred; else the text after the title.
 */
function pageSays(bytes: Uint8Array, title: string | undefined): string {
	const text = Buffer.from(bytes.subarray(0, 32_768))
		.toString("utf8")
		.replace(/<(script|style)\b[\s\S]*?<\/\1\s*>/gi, " ")
		.replace(/<[^>]+>/g, " ")
		.replace(/&nbsp;/g, " ")
		.replace(/\s+/g, " ")
		.trim();
	const stated = /\bError:?\s*(\d{3})\s*,\s*(.{1,160}?)(?=\s+at\s+[A-Z][a-z]{2},|$)/.exec(text);
	if (stated) return `, saying "HTTP ${stated[1]}: ${stated[2].trim()}"`;
	let rest = title && text.startsWith(title) ? text.slice(title.length).trim() : text;
	if (rest.length > 160) rest = `${rest.slice(0, 157)}...`;
	return rest ? `, saying "${rest}"` : "";
}

export class NotAnImage extends Error {
	readonly holds: string;
	constructor(holds: string) {
		super(`not an image: it ${holds}`);
		this.holds = holds;
	}
}

/** Why an image file cannot be attached, or undefined when it can. */
export function badImage(bytes: Uint8Array): string | undefined {
	const type = imageType(bytes);
	if (!type) return whatItHolds(bytes);
	if (cutShort(bytes, type)) return `is cut short: it stops before the end of the picture (${bytes.length} bytes) - an interrupted download`;
	return undefined;
}

/** An image part of a message whose bytes are not an image. */
function unreadable(part: unknown): boolean {
	if (!part || typeof part !== "object") return false;
	const p = part as { type?: unknown; data?: unknown };
	return p.type === "image" && typeof p.data === "string" && !imageType(Buffer.from(p.data.slice(0, 24), "base64"));
}

// What a page needs that a picture of it cannot explain. In test7 (2026-11-12) a gallery's six
// photos came from picsum.photos, which the egress proxy refuses: `view` drew six broken images
// and the model called the page "Perfect!". A browser with internet access would have shown six
// arbitrary stock photos captioned "White alpaca portrait" and the like. So a page's view says
// which local files it asks for are not there, which pages it links to do not exist, which
// remote hosts this render could not reach, and when a host serves placeholder pictures.
/** Hosts that serve whatever picture they like, never the one a caption describes. */
const PLACEHOLDER_HOSTS =
	/(^|\.)(picsum\.photos|placehold\.co|placeholder\.com|placekitten\.com|loremflickr\.com|source\.unsplash\.com|dummyimage\.com|fakeimg\.pl|lorempixel\.com|placeimg\.com)$/i;
const URL_IN_CSS = /url\(\s*["']?([^"')]+?)["']?\s*\)/gi;
const REMOTE = /^(https?:)?\/\//i;
/** HTML pages under `root` (four folders down at most, no hidden ones) changed since `since`, newest first. */
export function recentPages(root: string, since: number, limit = 40): string[] {
	const found: { path: string; mtime: number }[] = [];
	let seen = 0;
	const walk = (dir: string, depth: number) => {
		let entries: import("node:fs").Dirent[];
		try {
			entries = readdirSync(dir, { withFileTypes: true });
		} catch {
			return;
		}
		for (const e of entries) {
			if (++seen > 20000 || e.name.startsWith(".") || e.name === "node_modules") continue;
			const path = join(dir, e.name);
			if (e.isDirectory()) {
				if (depth < 4) walk(path, depth + 1);
			} else if (/\.html?$/i.test(e.name)) {
				try {
					const mtime = statSync(path).mtimeMs;
					if (mtime >= since) found.push({ path, mtime });
				} catch {
					// gone
				}
			}
		}
	};
	walk(root, 0);
	return found.sort((a, b) => b.mtime - a.mtime).slice(0, limit).map((f) => f.path);
}

/** The tools that write or edit a file the model names: a page written with one is compared at the end of the run. */
const PAGE_WRITERS = new Set(["write", "edit", "replace", "replace_match", "insert"]);

export interface PageResources {
	/** Files the page draws (images, stylesheets, scripts) that do not exist, relative to it. */
	missing: string[];
	/** Local pages it links to that do not exist. */
	links: string[];
	/** Remote hosts it draws from, with how many references each. */
	remote: Map<string, number>;
	/** Of those, the hosts its pictures come from (an <img>, or one an onerror handler swaps in). */
	pictures?: Map<string, number>;
	/** Files a local stylesheet asks for that do not exist: sheet -> files, both relative to the page. */
	fromSheets: Map<string, string[]>;
	/** Local image files it draws that are not images (a saved error page), with what they hold. */
	broken: { file: string; holds: string }[];
}

/** What an HTML file pulls in or links to, checked against the disk. */
export function pageResources(file: string): PageResources {
	const html = readFileSync(file, "utf8");
	const dir = dirname(file);
	const out: PageResources = { missing: [], links: [], remote: new Map(), pictures: new Map(), fromSheets: new Map(), broken: [] };
	const seen = new Set<string>();
	const check = (raw: string, base: string, kind: "resource" | "link", sheet?: string, picture = false) => {
		const ref = raw.trim().replace(/&amp;/g, "&");
		if (!ref || ref.startsWith("#") || /^(data|javascript|mailto|tel|about|blob):/i.test(ref)) return;
		if (REMOTE.test(ref)) {
			if (kind === "link") return; // a link to another site is not drawn
			try {
				const host = new URL(ref.startsWith("//") ? `https:${ref}` : ref).hostname;
				out.remote.set(host, (out.remote.get(host) ?? 0) + 1);
				if (picture) out.pictures?.set(host, (out.pictures.get(host) ?? 0) + 1);
			} catch {
				// not a URL after all
			}
			return;
		}
		let path = ref.split(/[?#]/)[0];
		if (!path) return;
		try {
			path = decodeURIComponent(path);
		} catch {
			// keep it as written
		}
		const target = path.startsWith("file://") ? fileURLToPath(path) : resolve(base, path);
		if (seen.has(`${kind} ${target}`)) return;
		seen.add(`${kind} ${target}`);
		const shown = relative(dir, target) || path;
		if (existsSync(target)) {
			// test10: images/earthworm.jpg was a saved "Wikimedia Error" page - there, and broken.
			if (kind === "resource" && kindOf(target) in PASSTHROUGH) {
				try {
					const holds = badImage(readFileSync(target));
					if (holds) out.broken.push({ file: shown, holds });
				} catch {
					// unreadable: the browser will say so
				}
			}
			return;
		}
		if (sheet) out.fromSheets.set(sheet, [...(out.fromSheets.get(sheet) ?? []), shown]);
		else (kind === "link" ? out.links : out.missing).push(shown);
	};
	for (const m of html.matchAll(/<(img|script|source|iframe|audio|video|embed|track|input)\b[^>]*?\ssrc\s*=\s*["']([^"']+)["']/gi))
		check(m[2], dir, "resource", undefined, m[1].toLowerCase() === "img");
	// test14: four missing pictures were given onerror="this.src='https://via.placeholder.com/...'" - a
	// stand-in from another site, in a site asked for "for local use".
	for (const m of html.matchAll(/\son\w+\s*=\s*(["'])([\s\S]*?)\1/gi))
		for (const s of m[2].replace(/&quot;/g, '"').replace(/&#39;/g, "'").matchAll(/\.src\s*=\s*(?:'([^']+)'|"([^"]+)"|`([^`$]+)`)/g))
			check(s[1] ?? s[2] ?? s[3], dir, "resource", undefined, true);
	for (const m of html.matchAll(/\sposter\s*=\s*["']([^"']+)["']/gi)) check(m[1], dir, "resource");
	for (const m of html.matchAll(/<link\b[^>]*>/gi)) {
		const rel = /\srel\s*=\s*["']([^"']+)["']/i.exec(m[0])?.[1] ?? "";
		const href = /\shref\s*=\s*["']([^"']+)["']/i.exec(m[0])?.[1];
		if (!href || !/stylesheet|icon|preload|manifest/i.test(rel)) continue;
		check(href, dir, "resource");
		if (!/stylesheet/i.test(rel) || REMOTE.test(href)) continue;
		const css = resolve(dir, href.split(/[?#]/)[0]);
		try {
			for (const u of readFileSync(css, "utf8").matchAll(URL_IN_CSS)) check(u[1], dirname(css), "resource", relative(dir, css));
		} catch {
			// missing, and already counted
		}
	}
	for (const m of html.matchAll(URL_IN_CSS)) check(m[1], dir, "resource");
	for (const m of html.matchAll(/<a\b[^>]*?\shref\s*=\s*["']([^"']+)["']/gi)) check(m[1], dir, "link");
	return out;
}

/**
 * The note under a page's picture. `rejected` holds the hosts the egress proxy refused during the
 * render (undefined when that is unknown); `proxied` says whether the render went through it at all.
 */
export function resourceNote(res: PageResources, proxied: boolean, rejected: Set<string> | undefined): string | undefined {
	const lines: string[] = [];
	const list = (items: string[]) => items.slice(0, 8).join(", ") + (items.length > 8 ? ` and ${items.length - 8} more` : "");
	if (res.missing.length)
		lines.push(`Missing: ${list(res.missing)} - the page asks for ${res.missing.length > 1 ? "these files, which are" : "this file, which is"} not there: broken in any browser.`);
	// test8: every page said "Missing: images/deer-hero.jpg" - the stylesheet's, for the one page with a hero.
	for (const [sheet, files] of res.fromSheets ?? []) {
		const many = files.length > 1;
		lines.push(
			`${sheet} asks for ${list(files)}, which ${many ? "are" : "is"} not there: wherever the stylesheet uses ` +
				`${many ? "them" : "it"}, a browser shows nothing in ${many ? "their" : "its"} place.`,
		);
	}
	for (const { file, holds } of res.broken ?? []) lines.push(`Not an image: ${file} - it ${holds}: broken in any browser.`);
	if (res.links.length) lines.push(`Links to pages that do not exist: ${list(res.links)}.`);
	const unreached = [...res.remote].filter(([host]) => (proxied ? rejected?.has(host) : true));
	if (unreached.length) {
		const count = unreached.reduce((n, [, k]) => n + k, 0);
		lines.push(
			`Not drawn here: ${unreached.map(([host, n]) => `${n} from ${host}`).join(", ")} - ` +
				(proxied ? "the egress proxy refuses that host" : "this render reaches no other host") +
				`, so ${count > 1 ? "they show" : "it shows"} as broken above; a browser with internet access loads ${count > 1 ? "them" : "it"}.`,
		);
	}
	const pictures = [...(res.pictures ?? [])];
	if (pictures.length) {
		const count = pictures.reduce((n, [, k]) => n + k, 0);
		lines.push(
			`Pictures from other sites: ${pictures.map(([host, n]) => `${n} from ${host}`).join(", ")} - not copies in this ` +
				`folder: ${count > 1 ? "they show" : "it shows"} only while the reader is online and that site serves ` +
				`${count > 1 ? "them" : "it"}. For a site that works offline, download each into it and point the page at the file.`,
		);
	}
	const placeholders = [...res.remote.keys()].filter((host) => PLACEHOLDER_HOSTS.test(host));
	if (placeholders.length)
		lines.push(
			`${placeholders.join(", ")} ${placeholders.length > 1 ? "serve" : "serves"} arbitrary placeholder pictures, not what ` +
				"a caption or alt text describes: in a browser those images will not show what the page says they do.",
		);
	return lines.length ? lines.join("\n") : undefined;
}

// The parts every page of a site repeats, compared across all its pages. In test8 and test9
// (2026-11-12) the model was asked to "check the visual renderings between each subpage for
// consistency", was shown them together with "list every difference", and answered "Perfect!
// All pages are rendering with complete visual consistency" over six pages with four different
// footers, one "(c) 2024" among "(c) 2026" and a homepage linking a stylesheet that did not
// exist. Telling it to look was not enough, so `view` of a page now says what differs.
const REPEATED = ["header", "nav", "footer"] as const;
const COPYRIGHT = /(?:©|&copy;|&#169;|&#xa9;|\bcopyright\b)(?:\s|&nbsp;)*(?:\d{4}\s*(?:-|–|&ndash;)\s*)?(\d{4})/gi;
const SITE_MAX_PAGES = 40;
/** Class names that mark the current page's link: meant to differ from page to page. */
const CURRENT = /^(?:active|current|selected|is-active|current-page|current-menu-item)$/i;

function firstElement(html: string, tag: string): string | undefined {
	return new RegExp(`<${tag}\\b[^>]*>[\\s\\S]*?</${tag}\\s*>`, "i").exec(html)?.[0];
}

/**
 * The site's header: the first <header> holding the navigation or a link home. A page's own title
 * banner - `<header class="page-header"><h1>Common Worm Species</h1>` - is meant to differ from page
 * to page; test11 (2026-11-13) was told "header: 5 versions" of exactly those.
 */
function siteHeader(html: string): string | undefined {
	for (const m of html.matchAll(/<header\b[^>]*>[\s\S]*?<\/header\s*>/gi))
		if (/<nav\b/i.test(m[0]) || /\shref\s*=\s*["'](?:\.\/|\/|index\.html?)["']/i.test(m[0])) return m[0];
	return undefined;
}

/** A part as compared: one line per opening tag or run of text, without comments, spacing, or which link is current. */
export function partLines(part: string): string[] {
	return part
		.replace(/<!--[\s\S]*?-->/g, "")
		.replace(/\s(?:aria-current|aria-selected)\s*=\s*(["'])[^"']*\1/gi, "")
		.replace(/\sclass\s*=\s*(["'])([^"']*)\1/gi, (_m, _q, cls: string) => {
			const kept = cls.split(/\s+/).filter((c) => c && !CURRENT.test(c));
			return kept.length ? ` class="${kept.join(" ")}"` : "";
		})
		.replace(/\s+/g, " ")
		.replace(/\s*(<[^>]+>)\s*/g, "\n$1\n")
		.split("\n")
		.map((l) => l.trim())
		.filter((l) => l && !l.startsWith("</"));
}

const names3 = (items: string[]) => (items.length > 4 ? `${items.slice(0, 3).join(", ")} and ${items.length - 3} more` : items.join(", "));

/** How the pages of the site in `dir` differ in what they all repeat, or undefined for one page. `place` is "in site/" or "here". */
export function compareSite(dir: string, place: string = `in ${dir}/`): string | undefined {
	let names: string[];
	try {
		names = readdirSync(dir).filter((n) => /\.html?$/i.test(n)).sort().slice(0, SITE_MAX_PAGES);
	} catch {
		return undefined;
	}
	if (names.length < 2) return undefined;
	const pages = names.map((n) => {
		try {
			return readFileSync(join(dir, n), "utf8");
		} catch {
			return "";
		}
	});
	const lines: string[] = [];
	const same: string[] = [];
	const cut = (l: string) => `"${l.length > 90 ? `${l.slice(0, 87)}...` : l}"`;
	for (const tag of REPEATED) {
		const label = tag === "nav" ? "navigation" : tag;
		const versions = new Map<string, string[]>();
		pages.forEach((html, i) => {
			let part = tag === "header" ? siteHeader(html) : firstElement(html, tag);
			if (part && tag === "header") part = part.replace(/<nav\b[\s\S]*?<\/nav\s*>/gi, "");
			const key = part === undefined ? "" : partLines(part).join("\n");
			versions.set(key, [...(versions.get(key) ?? []), names[i]]);
		});
		if (versions.size === 1) {
			if (!versions.has("")) same.push(label);
			continue;
		}
		const ranked = [...versions].sort((a, b) => b[1].length - a[1].length || (a[0] === "" ? 1 : -1));
		const [common, commonPages] = ranked[0];
		lines.push(`- ${label}: ${versions.size} versions - ${ranked.map(([, ps]) => ps.join(", ")).join(" | ")}.`);
		const base = new Set(common.split("\n"));
		for (const [key, ps] of ranked.slice(1, 4)) {
			const who = `${ps[0]}${ps.length > 1 ? ` (and ${ps.length - 1} more)` : ""}`;
			if (key === "") {
				lines.push(`    ${who}: no <${tag}> at all.`);
				continue;
			}
			const mine = key.split("\n");
			const own = new Set(mine);
			const extra = mine.filter((l) => !base.has(l)).slice(0, 3);
			const lacking = common ? [...base].filter((l) => !own.has(l)).slice(0, 3) : [];
			const parts = [extra.length ? `has ${extra.map(cut).join(", ")}` : "", lacking.length ? `lacks ${lacking.map(cut).join(", ")}` : ""];
			lines.push(`    ${who}, unlike ${commonPages[0]}: ${parts.filter(Boolean).join("; ") || "the same lines in another order"}.`);
		}
	}
	const group = (key: (html: string) => string | undefined) => {
		const out = new Map<string, string[]>();
		pages.forEach((html, i) => {
			const k = key(html);
			if (k !== undefined) out.set(k, [...(out.get(k) ?? []), names[i]]);
		});
		return [...out].sort((a, b) => b[1].length - a[1].length);
	};
	const years = group((html) => [...new Set([...html.matchAll(COPYRIGHT)].map((m) => m[1]))].join("/") || undefined);
	if (years.length > 1) lines.push(`- copyright year: ${years.map(([y, ps]) => `${y} on ${names3(ps)}`).join("; ")}.`);
	const used = new Set<string>();
	const sheets = group((html) => {
		const hrefs: string[] = [];
		for (const m of html.matchAll(/<link\b[^>]*>/gi)) {
			const href = /\shref\s*=\s*["']([^"'?#]+)/i.exec(m[0])?.[1];
			if (href && /\srel\s*=\s*["'][^"']*stylesheet/i.test(m[0]) && !REMOTE.test(href)) hrefs.push(relative(dir, resolve(dir, href)));
		}
		for (const m of html.matchAll(/<script\b[^>]*\ssrc\s*=\s*["']([^"'?#]+)/gi)) if (!REMOTE.test(m[1])) used.add(relative(dir, resolve(dir, m[1])));
		for (const h of hrefs) used.add(h);
		return hrefs.join(", ") || "no stylesheet";
	});
	if (sheets.length > 1) lines.push(`- stylesheets: ${sheets.map(([h, ps]) => `${h} on ${names3(ps)}`).join("; ")}.`);
	// What the pages draw, from the pages and their local stylesheets: what is left over is not.
	const local = (ref: string, base: string) => (REMOTE.test(ref) || /^(?:data|#|mailto|javascript):/i.test(ref) ? undefined : relative(dir, resolve(base, ref.split(/[?#]/)[0])));
	const linked = new Set<string>();
	for (const html of pages) {
		for (const m of html.matchAll(/\s(?:src|poster|href)\s*=\s*["']([^"']+)["']/gi)) {
			const f = local(m[1], dir);
			if (f) (/^<a\b/i.test(html.slice(html.lastIndexOf("<", m.index ?? 0), (m.index ?? 0) + 1)) ? linked : used).add(f);
		}
		for (const m of html.matchAll(/\ssrcset\s*=\s*["']([^"']+)["']/gi))
			for (const part of m[1].split(",")) {
				const f = local(part.trim().split(/\s+/)[0] ?? "", dir);
				if (f) used.add(f);
			}
		for (const m of html.matchAll(URL_IN_CSS)) {
			const f = local(m[1], dir);
			if (f) used.add(f);
		}
	}
	for (const sheet of [...used].filter((f) => /\.css$/i.test(f))) {
		try {
			for (const m of readFileSync(join(dir, sheet), "utf8").matchAll(URL_IN_CSS)) {
				const f = local(m[1], dirname(join(dir, sheet)));
				if (f) used.add(f);
			}
		} catch {
			// missing: the page's own note says so
		}
	}
	// Stylesheets, scripts and pictures in the site that no page uses (test8's js/main.js; test10's
	// placeholder drawings and saved error pages beside the real photos).
	const unused: string[] = [];
	for (const sub of ["", "css", "js", "styles", "scripts", "assets", "images", "img", "pictures", "photos", "media"]) {
		try {
			for (const n of readdirSync(join(dir, sub)))
				if (/\.(?:css|m?js|png|jpe?g|gif|webp|svg|avif)$/i.test(n) && !used.has(join(sub, n))) unused.push(join(sub, n));
		} catch {
			// no such folder
		}
	}
	if (unused.length) lines.push(`- ${names3(unused)}: in the site, but no page uses ${unused.length > 1 ? "them" : "it"}.`);
	// A page no other page links to (test10's template.html, the parent's scaffold, left in the site).
	const orphans = names.filter((n) => !/^index\.html?$/i.test(n) && !linked.has(n));
	if (orphans.length) lines.push(`- ${names3(orphans)}: no page links to ${orphans.length > 1 ? "them" : "it"}.`);
	if (lines.length === 0)
		return same.length
			? `The ${names.length} pages ${place} have the same ${same.length > 1 ? `${same.slice(0, -1).join(", ")} and ${same[same.length - 1]}` : same[0]} (apart from which link is marked current).`
			: undefined;
	return [
		`Compared across the ${names.length} pages ${place}, in what every page repeats:`,
		...lines,
		...(same.length ? [`The same on every page: ${same.join(", ")}.`] : []),
		"Make the pages agree and clear out what nothing uses, unless a difference is meant, before you call them consistent.",
	].join("\n");
}

// A reply that calls pages consistent, or a page fine, over what this run's own view said. test8,
// test10, test11 and test13 (2026-11-12/13) each ended "Perfect! ... consistent" or "rendering
// correctly" right after a comparison listing four or five footer versions, or a page view saying
// seven of its pictures were "broken in any browser". The note goes in before the run settles, once.
const CONSISTENT = /\b(?:consistent|identical|uniform)\b|\b(?:complete|full|perfect|total|100%|visual)\s+(?:visual\s+)?consistency\b/i;
const RENDERS_FINE =
	/\b(?:render(?:s|ing|ed)?|display(?:s|ing|ed)?|show(?:s|ing)?|work(?:s|ing)?)\s+(?:\w+\s+)?(?:correctly|properly|fine|well|as expected|perfectly)\b|\blooks?\s+(?:good|great|correct|right|fine|perfect)\b/i;
/** A claim with a "not" or "in-" in front of it is not the claim. */
const NEGATED_BEFORE = /\b(?:not|no longer|isn't|aren't|wasn't|weren't|never)\s*$/i;

function claims(text: string, pattern: RegExp): boolean {
	const all = new RegExp(pattern.source, "gi");
	for (const m of text.matchAll(all)) if (!NEGATED_BEFORE.test(text.slice(Math.max(0, (m.index ?? 0) - 14), m.index))) return true;
	return false;
}

export interface ViewFindings {
	/** The last comparison of a site this run, when it listed differences: where, and its "- " lines. */
	differences?: { place: string; lines: string[] };
	/** The last view of a page this run, when it reported something broken: the page, and those lines. */
	broken?: { page: string; lines: string[] };
}

/** The note for a final reply that claims what this run's views contradicted, or undefined. */
export function claimNote(reply: string, found: ViewFindings): string | undefined {
	const parts: string[] = [];
	if (found.differences && claims(reply, CONSISTENT))
		parts.push(
			`Your reply calls the pages consistent, but the last comparison of the pages ${found.differences.place} listed:\n` +
				found.differences.lines.slice(0, 8).join("\n"),
		);
	if (found.broken && (claims(reply, RENDERS_FINE) || claims(reply, CONSISTENT)))
		parts.push(`Your reply says ${found.broken.page} is fine, but its last view reported:\n${found.broken.lines.slice(0, 8).join("\n")}`);
	if (parts.length === 0) return undefined;
	return (
		`${parts.join("\n\n")}\n\nFix what is not meant to be so and view again, or tell the user plainly what is still ` +
		"wrong and which differences are meant. Do not call the pages consistent or fine until a view says so."
	);
}

/** The lines of a page's note that say something on it is broken. */
export function brokenLines(note: string): string[] {
	return note
		.split("\n")
		.filter((l) => /^(?:Missing: |Not an image: |Links to pages that do not exist: |Not drawn here: )/.test(l) || / asks for .* not there: /.test(l));
}

/**
 * A note for a command that fetches from a placeholder host. test9 (2026-11-12), under
 * `pi --remote`, asked for alpaca photos "for local use" and got seven curls of
 * picsum.photos/seed/alpaca1... - a seed picks an arbitrary photo, never an alpaca.
 */
export function placeholderNote(command: string): string | undefined {
	const hosts = new Set<string>();
	for (const m of command.matchAll(/https?:\/\/([^/\s"'`)]+)/gi)) if (PLACEHOLDER_HOSTS.test(m[1])) hosts.add(m[1].toLowerCase());
	if (hosts.size === 0) return undefined;
	const named = [...hosts].join(", ");
	return (
		`${named} ${hosts.size > 1 ? "serve" : "serves"} an arbitrary picture for any address, whatever its seed, size or ` +
		"keywords say: not the subject the page or caption names. " +
		(process.env.PI_ELM_REMOTE === "1"
			? "For real pictures, find them with web_search (Wikimedia Commons has freely licensed photos), download the " +
				"image file itself, look at each one, and record its source and licence for a credit."
			: "This session cannot reach the web for real ones (that needs `pi --remote`): say so to the user rather than " +
				"captioning a stand-in as the real thing.")
	);
}

/** The egress proxy's log, where it records each host it refuses. */
function egressLog(): string | undefined {
	return process.env.PI_CODING_AGENT_DIR ? join(process.env.PI_CODING_AGENT_DIR, "egress.log") : undefined;
}

function logSize(file: string | undefined): number {
	try {
		return file ? statSync(file).size : -1;
	} catch {
		return -1;
	}
}

/** Hosts the proxy refused after `offset` bytes of its log. */
export function rejectedAfter(file: string | undefined, offset: number): Set<string> | undefined {
	if (!file || offset < 0) return undefined;
	try {
		const text = readFileSync(file).subarray(offset).toString("utf8");
		return new Set([...text.matchAll(/ REJECTED ([^\s:]+)(?::\d+)?/g)].map((m) => m[1]));
	} catch {
		return undefined;
	}
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

/**
 * Why MuPDF cannot decode these bytes as a picture, or undefined when it can (or the type is GIF or
 * WebP, which it does not read). A right first few bytes are not a picture: auto08 (2026-11-13) wrote
 * eleven 129-byte "JPEGs" - a JFIF header and nothing after it - which were attached, and the gateway
 * answered "400 Failed to load image" and ended the session.
 */
export async function undecodable(bytes: Uint8Array, type: string | undefined): Promise<string | undefined> {
	if (!type || !/jpeg|png|tiff|bmp/.test(type) || bytes.length > 40e6) return undefined;
	const m = await mupdf();
	// biome-ignore lint/suspicious/noExplicitAny: mupdf's runtime shape
	let image: any;
	try {
		image = new m.Image(bytes);
		image.toPixmap()?.destroy?.();
		return undefined;
	} catch (error) {
		return String(error).replace(/^Error:\s*/, "").slice(0, 120);
	} finally {
		image?.destroy?.();
	}
}

/** "1-3,7" -> [0,1,2,6], clipped to the document. */
function pageList(spec: string | undefined, count: number): number[] {
	if (!spec?.trim()) return Array.from({ length: count }, (_, i) => i);
	const out = new Set<number>();
	for (const part of spec.split(",")) {
		const [a, b] = part.split("-").map((s) => s.trim());
		// "3," and "2,,5": an empty part selects nothing (a lone "-" is still every page)
		if (!a && b === undefined) continue;
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
	const type = imageType(bytes);
	if (ext in PASSTHROUGH) {
		const bad = badImage(bytes);
		if (bad) throw new NotAnImage(bad);
		const why = await undecodable(bytes, type);
		if (why) throw new NotAnImage(`does not decode as a picture (${why}): a hand-made or damaged file, ${bytes.length} bytes`);
	}
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
	if (type && ext in PASSTHROUGH && (pixels === undefined || pixels <= MAX_SIDE)) {
		return { pages: 1, shown: [0], content: [{ type: "image", data: bytes.toString("base64"), mimeType: type }] };
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
			} else if (entry.isFile() && figure(entry.name)) {
				if (recent(path, since)) found.push(path);
			}
		}
	};
	walk(root, 0);
	return found;
}

/** A command that fetches or unpacks in bulk. */
const BULK_COMMAND = /\b(?:git\s+clone|wget|curl|tar\s|unzip|7z\s|pip3?\s+download|huggingface-cli|hf\s+download|kaggle|aria2c|rsync|svn\s+checkout)\b/;

/**
 * What a bulk command added under `root` since `since`, when it is a lot. auto08b (2026-11-13): asked for
 * a frog website, workflow agents downloaded a 410 MB dataset of 7,796 images and cloned two dataset
 * repositories into the user's folder, and nobody said so.
 */
export function bulkNote(command: string, root: string, since: number, minBytes = 100e6, minFiles = 2000): string | undefined {
	if (!BULK_COMMAND.test(command)) return undefined;
	let bytes = 0;
	let files = 0;
	let entries = 0;
	const tops = new Map<string, number>();
	const walk = (dir: string, depth: number, top: string) => {
		if (depth > 6 || entries > 50000) return;
		let list: import("node:fs").Dirent[];
		try {
			list = readdirSync(dir, { withFileTypes: true });
		} catch {
			return;
		}
		for (const entry of list) {
			if (++entries > 50000) return;
			const path = join(dir, entry.name);
			const under = top || entry.name;
			if (entry.isDirectory()) {
				if (entry.name !== ".pi" && entry.name !== "node_modules") walk(path, depth + 1, under);
			} else if (entry.isFile()) {
				try {
					const st = statSync(path);
					if (st.mtimeMs < since) continue;
					bytes += st.size;
					files += 1;
					tops.set(under, (tops.get(under) ?? 0) + st.size);
				} catch {
					// gone
				}
			}
		}
	};
	walk(root, 0, "");
	if (bytes < minBytes && files < minFiles) return undefined;
	const mb = (n: number) => `${Math.round(n / 1e6)} MB`;
	const where = [...tops].sort((a, b) => b[1] - a[1]).slice(0, 4).map(([t, n]) => `${t} (${mb(n)})`).join(", ");
	return (
		`[view-outputs] This command added ${files} files, ${mb(bytes)}, to the project folder: ${where}. Keep only what ` +
		"the work uses - a few pictures, not a dataset - and delete the rest before you report, or tell the user why it is needed."
	);
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
	/** folder -> the site comparison last given for it, and in which turn, so an unchanged one is not repeated in full. */
	const siteSaid = new Map<string, { text: string; turn: number }>();
	let turn = 0;
	pi.on("turn_start", () => {
		turn++;
	});
	/** What this run's views found, for the reply check at the end of it. */
	let found: ViewFindings = {};
	let claimNoted = false;
	/** Folders this run wrote pages in, with its own tools. */
	let pageDirs = new Set<string>();
	let runStarted = Date.now();
	let launchedThisRun = false;
	pi.on("agent_start", () => {
		found = {};
		claimNoted = false;
		pageDirs = new Set();
		runStarted = Date.now();
		launchedThisRun = false;
	});
	pi.on("agent_before_settle", async (event, ctx) => {
		// A run that started background work ends on an interim reply: its children are still writing. auto09
		// (2026-11-13) viewed index.html while four siblings wrote the pages it links to, said it was ready, and
		// was sent back about "pages that do not exist" - a turn spent polling. The run their notices start
		// is the one that ends the work, and is checked.
		if (claimNoted || launchedThisRun) return undefined;
		const last = [...event.context.contextMessages].reverse().find((m) => m.role === "assistant") as
			| { content?: unknown }
			| undefined;
		const reply = Array.isArray(last?.content)
			? (last.content as { type?: string; text?: string }[]).map((p) => (p.type === "text" ? p.text ?? "" : "")).join("\n")
			: "";
		// Pages this run made and never viewed - by its own tools, a sub-agent or a workflow agent - are
		// checked here. auto06 (2026-11-13) wrote five pages with three footers, viewed none, and called them
		// consistent; auto08b's workflow agents wrote six pages with fourteen missing pictures and a text file
		// named .jpg, and the reply said "100% Self-Consistency Verified".
		if (!found.differences && !found.broken && (claims(reply, CONSISTENT) || claims(reply, RENDERS_FINE))) {
			const cwd = ctx?.cwd ?? process.cwd();
			const pages = recentPages(cwd, runStarted);
			for (const page of pages) pageDirs.add(dirname(page));
			for (const dir of pageDirs) {
				const place = dir === cwd ? "here" : `in ${dir.startsWith(`${cwd}/`) ? relative(cwd, dir) : dir}/`;
				const listed = (compareSite(dir, place) ?? "").split("\n").filter((l) => l.startsWith("- "));
				if (listed.length) {
					found.differences = { place, lines: listed };
					break;
				}
			}
			for (const page of pages) {
				let note: string | undefined;
				try {
					note = resourceNote(pageResources(page), Boolean(process.env.HTTPS_PROXY), undefined);
				} catch {
					continue;
				}
				const broken = brokenLines(note ?? "");
				if (broken.length) {
					found.broken = { page: relative(cwd, page) || page, lines: broken };
					break;
				}
			}
		}
		if (!found.differences && !found.broken) return undefined;
		const note = claimNote(reply, found);
		if (!note) return undefined;
		claimNoted = true;
		return { entries: [{ type: "custom_message", customType: "view-outputs-claim", content: note, display: true }], continue: true };
	});

	// Each image in the conversation decoded once (keyed by its length and ends), so the check costs a
	// request nothing after the first. This covers attachments that never passed through here: pi's own
	// `read` of an image file, a sub-agent's result.
	const decoded = new Map<string, boolean>();
	const decodesOnce = async (part: unknown): Promise<boolean> => {
		const p = part as { type?: unknown; data?: unknown; mimeType?: unknown };
		if (!p || p.type !== "image" || typeof p.data !== "string") return true;
		const key = `${p.data.length}:${p.data.slice(0, 64)}:${p.data.slice(-64)}`;
		const known = decoded.get(key);
		if (known !== undefined) return known;
		const bytes = Buffer.from(p.data, "base64");
		const ok = !unreadable(part) && !(await undecodable(bytes, imageType(bytes)));
		decoded.set(key, ok);
		return ok;
	};
	pi.on("context", async (event) => {
		let changed = false;
		const messages = await Promise.all(
			event.messages.map(async (message) => {
				const content = (message as { content?: unknown }).content;
				if (!Array.isArray(content) || !content.some((part) => (part as { type?: unknown })?.type === "image")) return message;
				const good = await Promise.all(content.map(decodesOnce));
				if (good.every(Boolean)) return message;
				changed = true;
				const kept = content.map((part, i) =>
					good[i] ? part : { type: "text" as const, text: "[left out here: an attachment that was not a valid image]" },
				);
				return { ...message, content: kept } as typeof message;
			}),
		);
		return changed ? { messages } : undefined;
	});

	pi.on("tool_call", (event, ctx) => {
		// Coarse filesystem timestamps (1 s on some) can put a file written at
		// the very start of the call just before it.
		if (WATCHED.has(event.toolName)) started.set(event.toolCallId, Date.now() - 1500);
		const path = (event.input as { path?: unknown } | undefined)?.path;
		if (PAGE_WRITERS.has(event.toolName) && typeof path === "string" && /\.html?$/i.test(path))
			pageDirs.add(dirname(resolve(ctx?.cwd ?? process.cwd(), path.replace(/^~(?=\/)/, homedir()))));
	});

	pi.on("tool_result", async (event, ctx) => {
		const cwd = ctx?.cwd ?? process.cwd();
		if ((event.toolName === "subagent" || event.toolName === "workflow") && !event.isError) {
			const text = (event.content ?? []).map((c: { type?: string; text?: string }) => (c.type === "text" ? c.text ?? "" : "")).join("\n");
			if (/\bAsync\b|started in the background|running in the background/i.test(text)) launchedThisRun = true;
		}

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
		const bulk = event.toolName === "bash" ? bulkNote(command, cwd, since) : undefined;
		const stand = [placeholderNote(command), bulk].filter(Boolean).join("\n") || undefined;
		const withStand = (content: typeof event.content) => (stand ? [...content, { type: "text" as const, text: stand }] : content);
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
		if (fresh.length === 0) return stand ? { content: withStand(event.content) } : undefined;

		const name = (path: string) => (isAbsolute(path) && path.startsWith(`${cwd}/`) ? relative(cwd, path) : path);

		if (!seesImages(ctx)) {
			const note =
				`[view-outputs] This command wrote ${fresh.map(name).join(", ")}. This model cannot see images: ` +
				"have the qwen sub-agent examine them before reporting on them.";
			return { content: withStand([...event.content, { type: "text", text: note }]) };
		}

		const attached: Content[] = [];
		const skipped: string[] = [];
		/** what a non-image holds -> the files that hold it */
		const broken = new Map<string, string[]>();
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
				if (error instanceof NotAnImage) broken.set(error.holds, [...(broken.get(error.holds) ?? []), name(path)]);
				else skipped.push(`${name(path)}: ${String(error).replace(/^Error: /, "").slice(0, 240)}`);
			}
		}
		const notImages = [...broken].map(([holds, files]) => {
			const many = files.length > 1;
			return `Not ${many ? "images" : "an image"}: ${files.join(", ")} - ${many ? "each" : "it"} ${holds}.`;
		});
		if (notImages.length && [...broken.keys()].some((h) => /text|web page|empty|cut short/.test(h)))
			notImages.push(
				"A download that saved the server's error reply, or stopped part way, instead of the picture: nothing here " +
					"shows it. Check the URL works, fetch again with `curl -fL` (which fails on an HTTP error instead of " +
					"saving it), and look at what arrives before you use it.",
			);

		const note = [
			`[view-outputs] This command wrote ${fresh.length} figure/document file(s).` +
				(lines.length ? ` Attached below: ${lines.join("; ")}.` : ""),
			...notImages,
			"Examine every attached image before you report on it or build on it: does it show what was intended; " +
				"are axes labelled with units, ranges and scales sensible, legends and text legible and not overlapping; " +
				"are there empty, clipped or wrong panels; does a fit follow the data. Fix and regenerate what is wrong, " +
				"and describe what each figure shows in your report.",
			skipped.length ? `Not attached here - ${skipped.join("; ")}. Look at what can be shown with the view tool.` : "",
		]
			.filter(Boolean)
			.join("\n");
		return { content: withStand([...event.content, { type: "text", text: note }, ...attached]) };
	});

	pi.registerTool({
		name: "view",
		label: "View",
		description:
			"Look at a PDF or an image: renders PDF pages (and XPS, TIFF, BMP) to images you can see, with each page's " +
			`text layer, at most ${VIEW_MAX_PAGES} pages per call - ask for further pages with \`pages\`. ` +
			"Use it on every figure or PDF you produce or are given before you describe it, and on a PDF when its " +
			"layout, figures, tables or equations matter. PNG/JPEG also work with read. An HTML page is drawn as a " +
			"browser shows it (headless Chrome or Chromium, else Quick Look), with a note of any file, linked page or " +
			"remote image it could not show; give the .html file, not a URL - no server is needed. To compare pages or " +
			`figures, pass up to ${VIEW_MAX_FILES} in \`paths\`: they come back together. ` +
			"SVG, EPS/PS, HEIC and PSD are converted first with a command-line tool if the machine has one (resvg, " +
			"rsvg-convert, inkscape, ImageMagick, Ghostscript, epstopdf, sips, qlmanage).",
		parameters: Type.Object({
			path: Type.Optional(Type.String({ description: "File to view, relative to the working directory or absolute." })),
			paths: Type.Optional(
				Type.Array(Type.String(), {
					maxItems: VIEW_MAX_FILES,
					description: "Several files to view together, to compare them (instead of path).",
				}),
			),
			pages: Type.Optional(Type.String({ description: 'PDF pages to render, 1-based, e.g. "1-3,7". Default: from page 1.' })),
			text: Type.Optional(Type.Boolean({ description: "Include each PDF page's text layer (default true)." })),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const cwd = ctx?.cwd ?? process.cwd();
			const fail = (message: string) => ({ content: [{ type: "text" as const, text: message }], details: {}, isError: true });
			if (!seesImages(ctx)) return fail("This model cannot see images. Ask the qwen sub-agent to view the file.");
			const asked = params.paths?.length ? params.paths : params.path ? [params.path] : [];
			if (asked.length === 0) return fail("Give `path`, or `paths` to see several files together.");
			const one = async (given: string): Promise<{ content: Content[]; error?: boolean }> => {
				const problem = (text: string) => ({ content: [{ type: "text" as const, text }], error: true });
				// test7: a child gave `view` http://127.0.0.1:8080/index.html and got "no such file".
				if (/^https?:\/\//i.test(given))
					return problem(
						`${given}: view takes a file, not a URL. For a page this machine serves, view its .html file: it is ` +
							"drawn as a browser draws it, with its stylesheets and images, and no server is needed.",
					);
				const path = /^file:\/\//i.test(given) ? fileURLToPath(given) : resolve(cwd, given);
				if (!viewable(path)) return problem(`${given}: not an image, PDF or web page. Use read for text files.`);
				let size: number;
				try {
					size = statSync(path).size;
				} catch {
					return problem(`${given}: no such file.`);
				}
				if (size > MAX_FILE_BYTES) return problem(`${given}: ${Math.round(size / 1e6)} MB is too large to render.`);
				const page = ON_REQUEST.has(kind(path));
				const log = egressLog();
				const offset = page ? logSize(log) : -1;
				try {
					const result = await show(path, params.pages, VIEW_MAX_PAGES, params.text !== false);
					shownAt.set(path, statSync(path).mtimeMs);
					let text = header(path, result, cwd);
					if (page) {
						const note = resourceNote(pageResources(path), Boolean(process.env.HTTPS_PROXY), rejectedAfter(log, offset));
						if (note) text += `\n${note}`;
						const broken = brokenLines(note ?? "");
						const shown = path.startsWith(`${cwd}/`) ? relative(cwd, path) : path;
						if (broken.length) found.broken = { page: shown, lines: broken };
						else if (found.broken?.page === shown) found.broken = undefined;
					}
					return { content: [{ type: "text", text }, ...result.content] };
				} catch (error) {
					return problem(`${given}: could not be shown: ${String(error).replace(/^Error: /, "").slice(0, 300)}`);
				}
			};
			const results: { content: Content[]; error?: boolean }[] = [];
			for (const given of asked) results.push(await one(given));
			// The same stylesheet's missing file, said once for all the pages that share it.
			const said = new Set<string>();
			for (const r of results)
				for (const part of r.content)
					if (part.type === "text")
						part.text = part.text
							.split("\n")
							.filter((l) => {
								if (!/ asks for .* not there: wherever the stylesheet uses /.test(l)) return true;
								if (said.has(l)) return false;
								said.add(l);
								return true;
							})
							.join("\n");
			const content = results.flatMap((r) => r.content);
			const sites = [
				...new Set(
					asked
						.filter((given, i) => !results[i].error && ON_REQUEST.has(kind(given)))
						.map((given) => dirname(/^file:\/\//i.test(given) ? fileURLToPath(given) : resolve(cwd, given))),
				),
			];
			for (const dir of sites) {
				const place = dir === cwd ? "here" : `in ${dir.startsWith(`${cwd}/`) ? relative(cwd, dir) : dir}/`;
				const text = compareSite(dir, place);
				if (!text) continue;
				const listed = text.split("\n").filter((l) => l.startsWith("- "));
				if (listed.length) found.differences = { place, lines: listed };
				else if (found.differences?.place === place) found.differences = undefined;
				// test10: five views called together; the first to finish carried the comparison, and the four
				// listed before it said "given before" of something the model had not read yet.
				const said = siteSaid.get(dir);
				const note =
					said?.text !== text
						? text
						: said.turn < turn
							? `The comparison of the pages ${place} given before still holds: nothing they share has changed.`
							: `The comparison of the pages ${place} is in another \`view\` result of this turn.`;
				if (said?.text !== text) siteSaid.set(dir, { text, turn });
				content.push({ type: "text", text: note });
			}
			// The parts of a web page, for pages only: test15's two photos were told to compare their
			// "navigation, header, layout ... footer".
			const pagesShown = asked.filter((given, i) => !results[i].error && ON_REQUEST.has(kind(given))).length;
			if (results.filter((r) => !r.error).length > 1)
				content.push({
					type: "text",
					text:
						"Shown together to compare. Before you call them consistent, list every difference you can see " +
						(pagesShown > 1
							? "between them - navigation, header, layout, colours, fonts, spacing, images, footer - and say which are meant to differ."
							: "between them, and say which are meant to differ."),
				});
			return { content, details: {}, ...(results.every((r) => r.error) ? { isError: true } : {}) };
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
