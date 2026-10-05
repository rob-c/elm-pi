// Preloaded into pi's node by pi.orig (`node --import lib/node-guard.mjs`).
// Two jobs, both done before a line of pi runs.
//
// 1. Packages come from this install and nowhere else.
//    Node resolves a bare import by walking up from the importing file through
//    every ancestor's node_modules, and then the "global folders"
//    ~/.node_modules, ~/.node_libraries and $PREFIX/lib/node. An install at
//    ~/.local/share/elm-pi therefore also loads from ~/.local/share/node_modules,
//    ~/.local/node_modules and ~/node_modules - and a stray `npm install` run in
//    a home directory is exactly how a ~/node_modules comes to exist. A missing
//    optional dependency, or a peer the extensions expect, would quietly come
//    from there. The hook below refuses any resolution that lands in a
//    node_modules (or a global folder) outside the install, for require,
//    import and require.resolve. jiti, which loads the extensions, resolves
//    with its own resolver and never reaches this hook; the launcher covers it
//    by refusing to start while any ancestor of the install has a node_modules
//    (elm_external_module_dirs in lib/sandbox.sh).
//    Files outside node_modules are untouched: `pi -e ./ext.ts` and trusted
//    project extensions still load, they just cannot pull packages from outside.
//
//      ELM_PI_ALLOW_EXTERNAL_MODULES=1   switch the check off for one run
//
// 2. Hand the account's environment back to the agent's own commands.
//    pi.orig starts node without LD_LIBRARY_PATH, DYLD_*, OPENSSL_CONF and
//    friends, because the dynamic linker and OpenSSL read those once, at
//    process start, and a conda lib directory there can break node itself. The
//    agent's bash tool still needs them for the researcher's work, so pi.orig
//    parks them as ELM_PI_STASH__<NAME> and they are restored here, after node
//    is up and before pi spawns anything.
import { registerHooks } from "node:module";
import { realpathSync } from "node:fs";
import { dirname, sep } from "node:path";
import { fileURLToPath } from "node:url";

const STASH = "ELM_PI_STASH__";
for (const key of Object.keys(process.env)) {
  if (!key.startsWith(STASH)) continue;
  const name = key.slice(STASH.length);
  if (name) process.env[name] = process.env[key];
  delete process.env[key];
}

const ROOT = realpathSync(dirname(dirname(fileURLToPath(import.meta.url)))) + sep;
// Path segments that mean "a package directory", and the global folders.
const PACKAGE_DIRS = new Set(["node_modules", ".node_modules", ".node_libraries"]);

function outside(url) {
  if (typeof url !== "string" || !url.startsWith("file:")) return false;   // node:, data:
  let file;
  try { file = fileURLToPath(url); } catch { return false; }
  if (file.startsWith(ROOT)) return false;
  return file.split(sep).some((part) => PACKAGE_DIRS.has(part));
}

if (process.env.ELM_PI_ALLOW_EXTERNAL_MODULES !== "1") {
  registerHooks({
    resolve(specifier, context, nextResolve) {
      const result = nextResolve(specifier, context);
      if (outside(result.url)) {
        const error = new Error(
          `elm-pi: refusing to load "${specifier}" from ${fileURLToPath(result.url)} - ` +
          `packages load only from ${ROOT} (ELM_PI_ALLOW_EXTERNAL_MODULES=1 lifts this)`,
        );
        error.code = "ERR_MODULE_NOT_FOUND";
        throw error;
      }
      return result;
    },
  });
}
