// Preloaded into pi's node by pi.orig (`node --import lib/node-guard.mjs`), and
// into bootstrap.sh's extension load check. Two jobs, both done before a line
// of pi runs.
//
// 1. Packages come from this install and nowhere else, whatever the machine
//    has. elm-pi brings its own Node and its own packages; a node_modules
//    elsewhere - a stray `npm install` in a home folder, a global npm or
//    Homebrew tree, another project above the install - is never used, and its
//    being there changes nothing.
//    Node resolves a bare import by walking up from the importing file through
//    every ancestor's node_modules, and then the "global folders"
//    ~/.node_modules, ~/.node_libraries and $PREFIX/lib/node; a package missing
//    from the install would quietly come from there. Two loaders are covered:
//      - Node's own (require, import, require.resolve): a resolve hook refuses
//        any resolution that lands in a node_modules or global folder outside
//        the install;
//      - jiti, which loads pi's extensions: it resolves with its own resolver,
//        which never reaches that hook, and then evaluates each file itself
//        through vm.runInThisContext with the file as `filename`. The same rule
//        is applied there, so a file in a node_modules outside the install is
//        refused whoever found it.
//    Files outside node_modules are untouched: `pi -e ./ext.ts` and trusted
//    project extensions still load, they just cannot pull packages from outside.
//    Paths are compared after resolving symlinks, so an install reached
//    through one (macOS's /tmp, a linked home) still loads its own packages.
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
import { basename, dirname, join, sep } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

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

/**
 * Where a path really is: symlinks resolved. A file that does not exist is
 * placed by the deepest folder above it that does, so a link anywhere on the
 * way - into the install or out of it - is seen through either way.
 */
function realPath(file) {
  const rest = [];
  let head = file;
  for (;;) {
    try { return join(realpathSync(head), ...rest); } catch { /* not there: try its folder */ }
    const parent = dirname(head);
    if (parent === head) return file;
    rest.unshift(basename(head));
    head = parent;
  }
}

/** A file in a package directory that is not this install's. */
export function outsideFile(file) {
  const real = realPath(file);
  if (real.startsWith(ROOT)) return false;
  return real.split(sep).some((part) => PACKAGE_DIRS.has(part));
}

function outsideUrl(url) {
  if (typeof url !== "string" || !url.startsWith("file:")) return false;   // node:, data:
  let file;
  try { file = fileURLToPath(url); } catch { return false; }
  return outsideFile(file);
}

function refusal(what, file) {
  const error = new Error(
    `elm-pi: refusing to load "${what}" from ${file} - ` +
    `packages load only from ${ROOT} (ELM_PI_ALLOW_EXTERNAL_MODULES=1 lifts this)`,
  );
  error.code = "ERR_MODULE_NOT_FOUND";
  return error;
}

if (process.env.ELM_PI_ALLOW_EXTERNAL_MODULES !== "1") {
  registerHooks({
    resolve(specifier, context, nextResolve) {
      const result = nextResolve(specifier, context);
      if (outsideUrl(result.url)) throw refusal(specifier, fileURLToPath(result.url));
      return result;
    },
  });

  // jiti calls vm.runInThisContext through the module object, so replacing the
  // property here is what it calls.
  const runInThisContext = vm.runInThisContext;
  vm.runInThisContext = function (code, options, ...rest) {
    const filename = typeof options === "string" ? options : options?.filename;
    if (typeof filename === "string" && filename && outsideFile(filename)) throw refusal(filename, filename);
    return runInThisContext.call(this, code, options, ...rest);
  };
}
