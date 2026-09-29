#!/usr/bin/env python3
"""
patch-pi.py - remove /share and /bug from the installed pi release.

Both commands upload an entire session - every file the agent read, every
command output, anything pasted - to a third party:

    /share   exports the session and publishes it as a GitHub gist, after first
             trying pi's own Radius gateway
    /bug     POSTs report.json, diagnostics.json and session.jsonl, the whole
             transcript, to https://radius.pi.dev/v1/bug-reports

pi offers no way to disable a built-in command. There is no `disabledCommands`
setting, and an extension cannot shadow one: the command merge filters
extension commands against the built-in names, so the built-in always wins.
Patching the shipped bundle is what is left.

Seven edits, in three layers:

  1. the two dispatcher branches, so the commands refuse and say why
  2. the two entries in the slash-command list, so they leave autocomplete
  3. the three upload functions, so any route that reaches them throws -
     including routes a future pi refactor might introduce

WHAT THIS IS NOT: a security control. Anyone can run `npm install` and get an
unpatched pi, and the bash tool can upload a file with curl regardless. It
removes an accident, not an intent. The network is the only enforcement point;
see LOCKDOWN.md.

MAINTENANCE: the anchors below are minified source from a specific pi release.
They will eventually stop matching. That is handled deliberately: an anchor
that is neither present nor already patched is a hard error, so a pi upgrade
that moves this code fails the install instead of quietly restoring `/share`.
When that happens, re-derive the anchors and update them here. The bundle's
chunk files are content-hash-named, so nothing here may hardcode a filename.

    ./patch-pi.py            apply (idempotent)
    ./patch-pi.py --check    verify, non-zero if any edit is missing
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE = HERE / "node_modules/@earendil-works/pi-coding-agent/dist/bundle"

REFUSAL = (
    "/share and /bug upload the whole session off-site and are disabled on "
    "this install. See LOCKDOWN.md."
)
THROW = "throw new Error('elm-pi: session uploads are disabled on this install');"

# (name, anchor, replacement, sentinel). Every anchor must appear exactly once
# across the bundle, and every replacement must be recognisable on a second run
# so that applying twice is a no-op.
#
# `sentinel` exists for the deletions, where "done" is the absence of the anchor
# and absence has two causes: we removed it, or a pi release reworded it. Those
# are indistinguishable without a second probe, so a deletion also asserts that
# a shorter, wording-independent fragment is gone. Anchor absent but sentinel
# present means the bundle moved under us, and that fails the install rather
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
    (
        "autocomplete: /share",
        '{name:"share",description:"Share session as a secret GitHub gist"},',
        "",
        'name:"share"',
    ),
    (
        "autocomplete: /bug",
        '{name:"bug",description:"Report a bug to the Pi developers",argumentHint:"<description>"},',
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
]


def main():
    check_only = "--check" in sys.argv[1:]

    if not BUNDLE.is_dir():
        print(f"patch-pi: no pi install at {BUNDLE}", file=sys.stderr)
        return 1

    files = sorted(BUNDLE.rglob("*.js"))
    sources = {f: f.read_text(encoding="utf-8", errors="surrogateescape") for f in files}

    changed, already, failed = [], [], []

    for name, anchor, replacement, sentinel in EDITS:
        # Ask "is it already done?" first. Several replacements keep the anchor
        # as their own prefix - the throw is inserted after the function opens -
        # so a present anchor does not mean an unpatched file, and checking the
        # other way round patches twice.
        if replacement:
            done = any(replacement in s for s in sources.values())
        else:
            done = not any(anchor in s for s in sources.values())
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

        total = sum(s.count(anchor) for s in sources.values())

        if total == 1:
            if check_only:
                failed.append(f"{name}: not applied")
            else:
                f = next(f for f, s in sources.items() if anchor in s)
                sources[f] = sources[f].replace(anchor, replacement, 1)
                changed.append(name)
        elif total > 1:
            failed.append(f"{name}: anchor matched {total} times, expected 1")
        else:
            failed.append(f"{name}: anchor not found and no patched form present")

    if failed:
        print("patch-pi: FAILED", file=sys.stderr)
        for line in failed:
            print(f"    {line}", file=sys.stderr)
        print(
            "    pi's bundle has changed. Re-derive the anchors in patch-pi.py\n"
            "    before trusting that /share and /bug are gone.",
            file=sys.stderr,
        )
        return 1

    if changed and not check_only:
        for f in files:
            if sources[f] != f.read_text(encoding="utf-8", errors="surrogateescape"):
                f.write_text(sources[f], encoding="utf-8", errors="surrogateescape")

    if check_only:
        print(f"    /share and /bug are disabled ({len(already)} edits in place)")
    elif changed:
        print(f"    disabled /share and /bug ({len(changed)} edits applied)")
    else:
        print(f"    /share and /bug already disabled ({len(already)} edits in place)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
