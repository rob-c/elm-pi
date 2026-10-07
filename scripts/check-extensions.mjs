// Loads every extension pi would load for this install - local extensions and
// every package in agent/settings.json - with pi's own resource loader, and
// reports any that fail. bootstrap.sh runs it after installing packages.
//
// Why not `pi --list-models`: that command returns before pi reports extension
// load errors, so a package that is on disk but does not load passed as healthy.
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const root = process.env.ELM_PI_INSTALL_DIR;
const agentDir = join(root, "agent");
const { DefaultResourceLoader } = await import(
  pathToFileURL(join(root, "node_modules/@earendil-works/pi-coding-agent/dist/index.js")).href
);

// An empty working directory, so no project's own .pi resources are mixed in.
const cwd = mkdtempSync(join(tmpdir(), "elm-pi-extcheck-"));
try {
  const loader = new DefaultResourceLoader({ cwd, agentDir });
  await loader.reload();
  const { extensions = [], errors = [] } = loader.getExtensions();
  for (const { path, error } of errors) {
    console.log(`    Failed to load extension "${path}": ${String(error).split("\n")[0]}`);
  }
  console.log(`    ${extensions.length} extensions loaded, ${errors.length} failed`);
  process.exitCode = errors.length ? 1 : 0;
} finally {
  rmSync(cwd, { recursive: true, force: true });
}
