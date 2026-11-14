#!/usr/bin/env python3
"""
patch-pi.py - the edits elm-pi keeps in code it does not own: pi's shipped
bundle, and the pi-permission-system package (the permission gate).

pi (the default; --bundle PATH patches a staged release)
--------------------------------------------------------

/share and /bug upload an entire session - every file the agent read, every
command output, anything pasted - to a third party:

    /share   exports the session and publishes it as a GitHub gist, after first
             trying pi's own Radius gateway
    /bug     POSTs report.json, diagnostics.json and session.jsonl, the whole
             transcript, to https://radius.pi.dev/v1/bug-reports

pi offers no way to disable a built-in command. There is no `disabledCommands`
setting, and an extension cannot shadow one: the command merge filters
extension commands against the built-in names, so the built-in always wins.
Patching the shipped bundle is what is left.

pi's own subcommands - `pi install|remove|uninstall|update|list|config|auth|mcp`
- manage pi's packages, provider credentials, model catalogues and MCP servers.
In this install each of those belongs to elm-pi: the package set is the
reviewed one bootstrap.sh builds from templates/, the only credential is the
ELM key in .env, the model list is agent/models.json, MCP is off, and
`pi update` is the launcher's. The launcher refuses them by name, saying what
to do instead (`pi auth login` used to reach the model as a prompt). pi refuses
them too, so the unwrapped CLI (pi.orig) and anything that reaches pi past the
launcher gets the same answer, and `pi --help` no longer lists them.

Nine edits for that, in four layers:

  1. the two dispatcher branches, so /share and /bug refuse and say why
  2. the two entries in the slash-command list, so they leave autocomplete
  3. the three upload functions, so any route that reaches them throws -
     including routes a future pi refactor might introduce
  4. the CLI: the subcommands refuse before pi dispatches any of them, and the
     Commands block leaves --help

WHAT THIS IS NOT: a security control. Anyone can run `npm install` and get an
unpatched pi, and the bash tool can upload a file with curl regardless. It
removes an accident, not an intent. The network is the only enforcement point;
see LOCKDOWN.md.

One more edit, of a different kind: retry jitter. pi waits exactly
baseDelayMs * 2^(attempt-1) before each retry of a failed model request. Every
sub-agent the gateway refuses in the same second therefore retries in the same
second, and is refused together again: measured on ELM, the 1.1/2.1/4.2/8.2/
16.2/32.2s waits did not vary at all between sessions (10th and 90th
percentiles equal). pi has no setting for jitter, so its delay function is
patched to scale each wait by a random factor between 0.75 and 1.25. The
schedule itself - ten retries, 1s doubling to 512s - is retry in
templates/settings.json (INSTALL.md, "Retry under a gateway storm").

The permission gate (--gate PACKAGE_DIR)
----------------------------------------

The permission modes - manual, auto, yolo (config/elm-pi.json
permissionModes; pi --manual/--auto/--yolo; /mode) - are applied by the gate,
where a child session's ask is already forwarded to the session you are
watching. The gate has a yolo switch but it is one global setting, shared by
every session of the install, and it has no switch at all for the other
direction. So it is patched to read the mode of the process it runs in,
PI_ELM_PERMISSION_MODE, which the launcher sets and sub-agents inherit:

  - yolo: the gate's own yolo, on for this process, so every ask is answered
    yes, including the ones it synthesises after resolution; a deny stays a deny
  - manual: every allow in the composed policy becomes an ask, except on the
    path and external_directory surfaces (where, not what) and skill, and
    except for the tools in PI_ELM_MANUAL_ALLOW (permissionModes.manualNoPrompt),
    which are allowed after the universal fallback so a later ask or deny for
    them still wins. Session approvals are applied after the floor, so "allow
    for this session" is not asked again.
  - auto, or no mode: the gate unchanged.

Both read the environment on every decision, so /mode takes effect at once.
Three edits: the yolo reader in index.ts, and in policy/permission-manager.ts
the floor and the function that computes it.

In manual, a sub-agent launch asks like any other call, and the agents it
starts run in auto when PI_ELM_APPROVED_AGENTS is auto (permissionModes.
approvedAgents; permission-mode.ts switches the run's own process). So the ask
says so: two more edits give a `subagent` launch asked in manual a note, and
make the dialog show an ask's notes - the gate builds them but has never
drawn them. Each has its own anchor in a file the edits above do not touch, so
an install patched before them takes them on its next run.

MAINTENANCE: the anchors below are source from specific releases. They will
eventually stop matching. That is handled deliberately: an anchor that is
neither present nor already patched is a hard error, so an upgrade that moves
this code fails the install instead of quietly restoring `/share`, or quietly
running a manual session as an auto one. When that happens, re-derive the
anchors and update them here. pi's bundle chunks are content-hash-named, so
nothing here may hardcode a filename.

    ./patch-pi.py                    apply to pi (idempotent)
    ./patch-pi.py --check            verify pi, non-zero if any edit is missing
    ./patch-pi.py --bundle PATH      patch a staged pi bundle before activation
    ./patch-pi.py --gate PATH        the same for the gate package at PATH
                                     (with or without --check)
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_BUNDLE = HERE / "node_modules/@earendil-works/pi-coding-agent/dist/bundle"

REFUSAL = (
    "/share and /bug upload the whole session off-site and are disabled on "
    "this install. See LOCKDOWN.md."
)
THROW = "throw new Error('elm-pi: session uploads are disabled on this install');"

# Every subcommand pi dispatches on its first argument.
SUBCOMMANDS = ("install", "remove", "uninstall", "update", "list", "config", "auth", "mcp")
# A JavaScript template literal: ${args[0]} is the subcommand pi was given.
SUBCOMMAND_REFUSAL = (
    "pi ${args[0]}: not available in this install - its packages, credentials, "
    "updates and models are managed by elm-pi (pi --help). See LOCKDOWN.md."
)

# (name, anchor, replacement, sentinel). An anchor is a string or a compiled
# pattern. Every anchor must appear exactly once
# across the files, and every replacement must be recognisable on a second run
# so that applying twice is a no-op.
#
# `sentinel` exists for the deletions, where "done" is the absence of the anchor
# and absence has two causes: we removed it, or a release reworded it. Those
# are indistinguishable without a second probe, so a deletion also asserts that
# a shorter, wording-independent fragment is gone. Anchor absent but sentinel
# present means the code moved under us, and that fails the install rather
# than quietly leaving the command in place.
EDITS = [
    (
        "dispatcher: /share",
        'if(text==="/share"){await this.handleShareCommand(),this.editor.setText("");return}',
        'if(text==="/share"){this.editor.setText(""),this.showError("%s");return}' % REFUSAL,
        None,
    ),
    (
        "dispatcher: /bug",
        'if(text==="/bug"||text.startsWith("/bug ")){let hint=text.slice(4).trim();'
        'this.editor.setText(""),await this.handleBugCommand(hint||void 0);return}',
        'if(text==="/bug"||text.startsWith("/bug ")){this.editor.setText(""),'
        'this.showError("%s");return}' % REFUSAL,
        None,
    ),
    # The two list entries are matched whatever their description says: the
    # wording is what pi changes (1.4.0 rewrote /share's), and a fixed string
    # turned each rewording into a failed install. The sentinel still catches
    # an entry that has moved or changed shape.
    (
        "autocomplete: /share",
        re.compile(r'\{name:"share",description:"[^"]*"\},'),
        "",
        'name:"share"',
    ),
    (
        "autocomplete: /bug",
        re.compile(r'\{name:"bug",description:"[^"]*",argumentHint:"[^"]*"\},'),
        "",
        'name:"bug"',
    ),
    (
        "upload: bug report to radius.pi.dev",
        "async function uploadBugReport(bundle,options={}){",
        "async function uploadBugReport(bundle,options={}){" + THROW,
        None,
    ),
    (
        "upload: share via radius.pi.dev",
        "async function tryShareViaRadius(tmpFile,context){",
        "async function tryShareViaRadius(tmpFile,context){" + THROW,
        None,
    ),
    (
        "upload: share via GitHub gist",
        "async function shareViaGist(tmpFile,context){",
        "async function shareViaGist(tmpFile,context){" + THROW,
        None,
    ),
    # main() runs `if(<offline setup>,await runAuthCommand(args))return;` before
    # it looks at any other subcommand; the refusal goes in front of it, in the
    # same condition, so nothing after it sees one of these.
    (
        "cli: pi's subcommands",
        "await runAuthCommand(args))return;",
        "%s.includes(args[0])&&(console.error(`%s`),process.exitCode=2,!0)"
        "||await runAuthCommand(args))return;"
        % (json.dumps(list(SUBCOMMANDS), separators=(",", ":")), SUBCOMMAND_REFUSAL),
        None,
    ),
    # The whole block, header to the blank line after it, whatever each line
    # says; the chalk import's minified name is not fixed either.
    (
        "help: the subcommand list",
        re.compile(r'\$\{[\w$]+\.bold\("Commands:"\)\}\n(?:  \$\{APP_NAME\} [^\n]*\n)+\n'),
        "",
        "auth <command>",
    ),
    # Retry jitter (see the docstring): the cap first, then the random factor, so
    # the longest wait spreads too instead of every session hitting the cap at
    # once. Used for agent-turn retries and for compaction's summary retries.
    (
        "retries: jitter",
        "return Math.min(safeDelay,policy.maxAgentDelayMs??DEFAULT_MAX_AGENT_RETRY_DELAY_MS)}",
        "return Math.round(Math.min(safeDelay,policy.maxAgentDelayMs??DEFAULT_MAX_AGENT_RETRY_DELAY_MS)"
        "*(.75+Math.random()*.5))/*elm-pi: retry jitter*/}",
        None,
    ),
]

# The gate's mode switch: see "The permission gate" above.
MANUAL_FLOOR = """\
/**
 * elm-pi (patch-pi.py --gate): the manual permission mode. Every allow in the
 * composed policy becomes an ask, except on the path and external_directory
 * families and skill - where a tool may reach and what it may load, not what
 * it may do - and for the tools named in PI_ELM_MANUAL_ALLOW, which keep their
 * own rules and are allowed after the universal fallback, so that a later ask
 * or deny for one of them still wins. Deny and ask pass through.
 */
function elmPiManualFloor(rules: Ruleset): Ruleset {
  const noPrompt = new Set(
    (process.env.PI_ELM_MANUAL_ALLOW ?? "")
      .split(",")
      .map((name) => name.trim())
      .filter(Boolean),
  );
  const keeps = (surface: string): boolean => {
    const family = surfaceFamilyOf(surface);
    return family === "path" || family === "external_directory" || surface === "skill" || noPrompt.has(surface);
  };
  let fallback = -1;
  rules.forEach((rule, index) => {
    if (rule.surface.includes("*")) fallback = index;
  });
  const allows = (template?: Rule): Ruleset =>
    [...noPrompt].map((surface) => ({
      surface,
      pattern: "*",
      action: "allow" as const,
      origin: template?.origin ?? "global",
      layer: template?.layer ?? "config",
    }));
  const out: Ruleset = fallback < 0 ? allows() : [];
  rules.forEach((rule, index) => {
    out.push(rule.action === "allow" && !keeps(rule.surface) ? { ...rule, action: "ask" } : rule);
    if (index === fallback) out.push(...allows(rule));
  });
  return out;
}

"""

GATE_EDITS = [
    (
        "yolo: the session's mode",
        "const isYoloEnabled = (): boolean => isYoloModeEnabled(configStore.current());",
        "const isYoloEnabled = (): boolean =>\n"
        '    process.env.PI_ELM_PERMISSION_MODE === "yolo" || isYoloModeEnabled(configStore.current());',
        None,
    ),
    (
        "manual: the floor",
        "    const fullRules: Ruleset = this.isYoloEnabled()\n"
        "      ? rewriteAsksToYolo(composedWithSession)\n"
        "      : composedWithSession;\n",
        "    const fullRules: Ruleset = this.isYoloEnabled()\n"
        "      ? rewriteAsksToYolo(composedWithSession)\n"
        '      : process.env.PI_ELM_PERMISSION_MODE === "manual"\n'
        "        ? [...elmPiManualFloor(composedRules), ...(sessionRules ?? [])]\n"
        "        : composedWithSession;\n",
        None,
    ),
    (
        "manual: the floor's function",
        "export class PermissionManager implements ScopedPermissionManager {",
        MANUAL_FLOOR + "export class PermissionManager implements ScopedPermissionManager {",
        None,
    ),
]

# A launch asked in manual, when its agents will run in auto (see "The permission gate").
LAUNCH_NOTE = (
    "if you allow it, the agents this starts work in auto mode: commands and edits in the project "
    "run without asking you; git push, installs and the like still ask"
)
GATE_EDITS += [
    (
        "manual: a launch's note",
        "      : inputPreviewEvidence(facts, isProxyMcpCheck(check)),\n    annotations: [],\n",
        "      : inputPreviewEvidence(facts, isProxyMcpCheck(check)),\n"
        "    // elm-pi (patch-pi.py --gate): in manual, the agents an approved launch starts run in auto\n"
        "    annotations:\n"
        '      process.env.PI_ELM_PERMISSION_MODE === "manual" &&\n'
        '      process.env.PI_ELM_APPROVED_AGENTS === "auto" &&\n'
        '      check.toolName === "subagent" &&\n'
        '      typeof facts.input === "object" &&\n'
        "      facts.input !== null &&\n"
        '      ["task", "tasks", "chain", "workflow"].some((key) => key in (facts.input as object))\n'
        '        ? [{ source: "elm-pi", text: "%s" }]\n'
        "        : [],\n" % LAUNCH_NOTE,
        None,
    ),
    (
        "dialog: an ask's notes",
        "    facts.push({ label: \"context\", text: context });\n  }\n  return facts;\n}\n",
        "    facts.push({ label: \"context\", text: context });\n  }\n"
        "  // elm-pi (patch-pi.py --gate): the notes an ask carries, such as what allowing a launch means\n"
        "  for (const note of payload.annotations) facts.push({ label: \"note\", text: note.text });\n"
        "  return facts;\n}\n",
        None,
    ),
]

# What each target is, where its files are, and what it says.
TARGETS = {
    "pi": {
        "edits": EDITS,
        "files": lambda root: sorted(root.rglob("*.js")),
        "missing": "no pi install at",
        "applied": "disabled /share, /bug and pi's subcommands, jittered retries",
        "already": "/share, /bug and pi's subcommands already disabled, retries already jittered",
        "checked": "/share, /bug and pi's subcommands are disabled, retries are jittered",
        "failed": "pi's bundle has changed. Re-derive the anchors in patch-pi.py\n"
                  "    before trusting that /share, /bug and pi's subcommands are gone\n"
                  "    and that retries are jittered.",
    },
    "gate": {
        "edits": GATE_EDITS,
        "files": lambda root: sorted((root / "src").rglob("*.ts")),
        "missing": "no permission gate at",
        "applied": "the permission modes added to the gate",
        "already": "the permission modes already in the gate",
        "checked": "the gate applies the permission modes",
        "failed": "pi-permission-system has changed. Re-derive the --gate anchors in\n"
                  "    patch-pi.py before trusting a manual or yolo session.",
    },
}


def count(anchor, source):
    return len(anchor.findall(source)) if isinstance(anchor, re.Pattern) else source.count(anchor)


def substitute(anchor, replacement, source):
    if isinstance(anchor, re.Pattern):
        return anchor.sub(replacement, source, count=1)
    return source.replace(anchor, replacement, 1)


def patch(target, root, check_only):
    spec = TARGETS[target]
    if not root.is_dir() or (target == "gate" and not (root / "src").is_dir()):
        print(f"patch-pi: {spec['missing']} {root}", file=sys.stderr)
        return 1

    files = spec["files"](root)
    sources = {f: f.read_text(encoding="utf-8", errors="surrogateescape") for f in files}

    changed, already, failed = [], [], []

    for name, anchor, replacement, sentinel in spec["edits"]:
        # Ask "is it already done?" first. Several replacements keep the anchor
        # as their own prefix - the throw is inserted after the function opens -
        # so a present anchor does not mean an unpatched file, and checking the
        # other way round patches twice.
        if replacement:
            done = any(replacement in s for s in sources.values())
        else:
            done = not any(count(anchor, s) for s in sources.values())
            if done and sentinel and any(sentinel in s for s in sources.values()):
                # The exact entry is gone but the command still is not. A
                # reworded description reads as "already patched" to the check
                # above, which is the one way this script can fail silently.
                failed.append(
                    f"{name}: anchor absent but {sentinel} is still in the bundle "
                    "- the wording changed, the command did not go"
                )
                continue
        if done:
            already.append(name)
            continue

        total = sum(count(anchor, s) for s in sources.values())

        if total == 1:
            if check_only:
                failed.append(f"{name}: not applied")
            else:
                f = next(f for f, s in sources.items() if count(anchor, s))
                sources[f] = substitute(anchor, replacement, sources[f])
                changed.append(name)
        elif total > 1:
            failed.append(f"{name}: anchor matched {total} times, expected 1")
        else:
            failed.append(f"{name}: anchor not found and no patched form present")

    if failed:
        print("patch-pi: FAILED", file=sys.stderr)
        for line in failed:
            print(f"    {line}", file=sys.stderr)
        print(f"    {spec['failed']}", file=sys.stderr)
        return 1

    if changed and not check_only:
        for f in files:
            if sources[f] != f.read_text(encoding="utf-8", errors="surrogateescape"):
                f.write_text(sources[f], encoding="utf-8", errors="surrogateescape")

    if check_only:
        print(f"    {spec['checked']} ({len(already)} edits in place)")
    elif changed:
        print(f"    {spec['applied']} ({len(changed)} edits applied)")
    else:
        print(f"    {spec['already']} ({len(already)} edits in place)")
    return 0


def main():
    check_only = False
    target, root = "pi", DEFAULT_BUNDLE
    args = iter(sys.argv[1:])
    for arg in args:
        if arg == "--check":
            check_only = True
        elif arg in ("--bundle", "--gate"):
            try:
                root = Path(next(args)).resolve()
            except StopIteration:
                print(f"patch-pi: {arg} requires a path", file=sys.stderr)
                return 2
            target = "pi" if arg == "--bundle" else "gate"
        else:
            print(f"patch-pi: unknown option: {arg}", file=sys.stderr)
            return 2
    return patch(target, root, check_only)


if __name__ == "__main__":
    sys.exit(main())
