// The site a session built, checked with view's own functions: every folder of pages compared, every
// page's resources, every image file's bytes.  node audit.mjs <view-outputs.ts> <project dir>
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, extname } from "node:path";
import { pathToFileURL } from "node:url";

const [source, root] = process.argv.slice(2);
const m = await import(pathToFileURL(source).href);
const files = [];
const walk = (dir, depth) => {
	for (const e of readdirSync(dir, { withFileTypes: true })) {
		if (e.name === ".pi" || e.name === "node_modules" || e.name === ".git") continue;
		const p = join(dir, e.name);
		if (e.isDirectory() && depth < 4) walk(p, depth + 1);
		else if (e.isFile()) files.push(p);
	}
};
walk(root, 0);
const out = { files: [], sites: [], pages: [], badImages: [] };
for (const f of files) out.files.push(`${relative(root, f)} (${statSync(f).size} B)`);
const dirs = [...new Set(files.filter((f) => /\.html?$/i.test(f)).map((f) => f.slice(0, f.lastIndexOf("/"))))];
for (const d of dirs) {
	const place = d === root ? "here" : `in ${relative(root, d)}/`;
	try { out.sites.push({ dir: relative(root, d) || ".", text: m.compareSite(d, place) ?? "(no comparison)" }); }
	catch (e) { out.sites.push({ dir: relative(root, d) || ".", text: `compareSite failed: ${e}` }); }
}
for (const f of files.filter((f) => /\.html?$/i.test(f))) {
	try {
		const note = m.resourceNote(m.pageResources(f), false, undefined);
		if (note) out.pages.push({ page: relative(root, f), note });
	} catch (e) { out.pages.push({ page: relative(root, f), note: `pageResources failed: ${e}` }); }
}
for (const f of files.filter((f) => /\.(png|jpe?g|gif|webp|bmp|avif)$/i.test(f))) {
	try {
		const holds = m.badImage(readFileSync(f));
		if (holds) out.badImages.push(`${relative(root, f)}: ${holds}`);
	} catch (e) { out.badImages.push(`${relative(root, f)}: check failed ${e}`); }
}
console.log(JSON.stringify(out));
