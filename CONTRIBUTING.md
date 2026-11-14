# Contributing to elm-pi

The repository is both source code and an installer. Changes should leave a fresh
install reproducible, an existing install upgradeable, and the ELM-only policy
intact.

## Before a commit

```bash
./scripts/check.sh
```

This runs Bash and Python syntax checks, unit and policy tests, ShellCheck when it
is installed, and TypeScript checking when `typescript` is installed in the
checkout (`npm install`), using the bundled Node or, without one, the `node` on
PATH. It says so when it skips the type check. CI runs the same checks on Linux
and macOS.

## Sources of truth

- `config/elm-pi.json`: Node version, model defaults, allowed and built-in
  providers, scrubbed credential variables, web-tool names and required local
  extensions.
- `package.json`: pi and development tooling.
- `templates/packages.json`: the pi extension packages npm installs;
  `templates/settings.json` `packages`: the ones pi loads.
- `config/versions.json`: the versions of both trees this repo last tested.
- `templates/`: generated agent code and initial configuration. Model strings use
  `@QWEN_MODEL@`, `@MISTRAL_MODEL@` and `@LLAMA_MODEL@`; `scripts/elm_config.py`
  renders them.

Do not edit generated files under `agent/` as the durable version of a change.

## Developing elm-pi with elm-pi

elm-pi can work on itself, in a clone - never in the install it runs on, which
its guards refuse to every write (protected-paths.ts for the tools,
command-guard.ts for the shell). A session started in a clone reads the
repository's own `AGENTS.md`, which gives it these steps:

```bash
scripts/dev-setup.sh                  # once: this clone becomes a working install, offline
scripts/new-extension <name> "<what it does>"   # extension, test, config entry, INSTALL.md row
scripts/check-extension <name>        # loads it with pi's own loader; registered, documented, tested?
```

`scripts/dev-setup.sh` copies Node, pi and the extension packages from the
install the shell runs under (`--from DIR` for another) as APFS clones or
reflinks, then runs `bootstrap.sh` in a clean environment, which finds every
tree at its expected version and only renders `agent/` - no network, which an
elm-pi session's egress proxy would refuse. Run again, it re-renders: that is
how an edited template reaches the clone's `agent/` for a live trial
(`<clone>/pi --auto -p ...` from a new folder outside the clone, made with
`mktemp -d`: the clone's `.pi/` is gitignored, and a tool that honours
.gitignore finds nothing there).

An install carries `typescript` and `typebox` (about 36 MB) for one reason:
`check-extension` type-checks an extension in a clone that has no network, and
dev-setup copies them over with the rest. A type check is what catches an import
left out of a tool's `renderCall`, which no load, test or `pi -p` run reaches;
`check-extension` also calls each tool's `renderCall` and `renderResult` once.

`scripts/check-extension` runs on the clone's own Node and pi after dev-setup,
else the running install's; `ELM_PI_PI_ROOT`, which its wrapper sets, is the
folder whose `node_modules` holds the pi it loads with. A new extension's test
uses `tests/extension_harness.py`: a few lines of JavaScript run against the
extension with a recording stand-in for pi.

## Updating npm dependencies

Both manifests ask for `latest` and no lockfiles are committed. What an install
gets depends on how it was asked:

- **`--update`**, which is what `pi update` runs: the latest of every direct
  dependency, as published now.
- **Anything else** - a fresh install, `--force`, `pi update --extensions`, a
  re-run that rebuilds a tree: the direct dependencies listed in
  `config/versions.json`, the versions this repo last ran its checks against.
  A dependency the file does not list resolves to `latest`. `PI_VERSION=x.y.z`
  overrides pi for one run. `--force-packages` (`pi update --extensions`) also
  returns pi to its pin when `pi update` moved it on.

Adding a package is one line in `templates/packages.json`, plus `npm:<name>`
in `templates/settings.json` if pi should load it as an extension, plus its
tested version in `config/versions.json`. This is the only route: the launcher
refuses `pi install` and `pi remove`, and bootstrap removes a package that is
in `agent/settings.json` but not in `templates/`.

```bash
./bootstrap.sh --update      # re-resolve and reinstall both trees
```

Each tree is stamped with a digest of its manifest and its section of
`config/versions.json` (`node_modules/.elm-pi-lock.sha256`, and the same file
under `agent/npm/node_modules`). A plain re-run reinstalls a tree when that
digest changes, so a pull that moves a pin reaches existing installs at their
next `./bootstrap.sh`, installer re-run or `pi update --extensions`. A pull that
moves no pin leaves a tree as it is, including on `pi update`'s latest. The
stamp cannot see `latest` moving on the registry: that is what `--update`
(`pi update`) is for.

An update is kept only if it passes the run's checks: pi has to load
`agent/models.json` with Qwen in it, and both config files have to match the
schemas the new pi ships (`scripts/check_config.py`). Otherwise the previous pi
and extension trees are put back. Each run that passes writes the exact
versions it is running to `agent/installed-versions.json`. To move the tested
set forward, update a checkout, try it, and commit what it recorded:

```bash
./bootstrap.sh --update && ./scripts/check.sh
cp agent/installed-versions.json config/versions.json
```

Runtime installs use `npm install --ignore-scripts`, and no package script is
re-enabled: the set has no native dependency to rebuild.

Two of the packages are patched at install: pi's bundle (`/share`, `/bug` and
pi's own subcommands) and `@gotgenes/pi-permission-system`, which applies the
permission modes (`patch-pi.py --gate`). Both patches are anchored to the
release they were written against and fail the install, on purpose, when a new
release moves the code. Moving either one forward means re-deriving its anchors
in `patch-pi.py`; `tests/test_permission_modes.py` then checks, against the
installed gate, that each mode still decides what it should.

What this trades away, deliberately: transitive dependencies are not pinned, so
a build is still not exactly reproducible, a bad upstream release can reach an
install on its next `pi update` - though one that breaks the config is rolled
back rather than kept - and nothing enforces
a minimum version of a transitive dependency. `npm audit` is no longer run by
the checks or by CI. If any of that becomes a problem, the mechanism to restore
is in git history before this change: exact versions in both manifests, committed
lockfiles, `npm ci`, `scripts/repair-transitives.sh`, `scripts/audit.sh`, and the
two tests that enforced them.

## Updating models or policy

Change `config/elm-pi.json`, not the rendered environment or generated agent files.
`configure.sh` records a gateway-resolved Qwen id in `agent/model-ids.json` and
updates every runtime consumer through `scripts/elm_config.py`.

When pi adds or renames a provider, `tests/test_project.py` fails and names it;
add its id to `builtinProviders` and its credential environment variables to
`providerCredentials`, as described in `LOCKDOWN.md`.

## Changing a model setting

Sampling, thinking levels, output limits, compat flags and task routes are
measured choices, not defaults: each is in `docs/tuning/decisions.json` with the
run it came from. To change one:

1. Measure it. `docs/tuning/harness/` has the A/B runner (`ab6.py`: arms in their
   own installs, run side by side on the same tasks), the task sets and their
   checks (`ab.py`, `ab2.py`, `hard.py`), and the compaction, suggestion and
   gateway probes. Check a new task against the untouched project (it must fail)
   and a hand-written solution (it must pass) before any model runs it.
2. Keep the results in `docs/tuning/<date>/` and add their table to
   `docs/tuning/harness/tables.py` and `docs/tuning/README.md`.
3. Change the template, record the decision in `docs/tuning/decisions.json`,
   and give bootstrap.sh the migration for existing installs if the key is one
   it reapplies.

`tests/test_tuning_evidence.py` fails when a README table no longer matches its
results or a recorded decision is not what the templates ship;
`tests/test_model_settings.py` and `tests/test_model_requests.py` check what each
model is configured with and what pi actually sends it.
