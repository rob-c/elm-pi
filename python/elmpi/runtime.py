"""agent/runtime.env: the install's model ids and policy, in one file.

config/elm-pi.json is the install's configuration; scripts/elm_config.py renders
the values the launcher, the shim and the extensions all need into
agent/runtime.env, one `export NAME=value` per line. The bash launcher sources
that file, which is fine for a file the installer writes and the agent cannot
(agent/ is protected), but this launcher reads it instead: a file in the
install must not be able to run code inside the process that decides what the
agent may do. The values are identical - the file is generated with shell
quoting, so parsing it with shlex gives back exactly what sourcing it would
have set.
"""

import json
import os
import re
import shlex

from elmpi.errors import Refusal, CANNOT_START

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def path(root):
    return os.path.join(root, "agent", "runtime.env")


def load(root, env):
    """Read runtime.env into `env`, or refuse to start without it."""
    source = path(root)
    if not os.path.isfile(source):
        raise Refusal("elm-pi runtime configuration is missing. Run %s."
                      % os.path.join(root, "bootstrap.sh"), code=CANNOT_START)
    with open(source, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    try:
        if "\0" in text:
            raise ValueError("it holds a NUL byte")
        # comments=True: a `#` line is a comment to the shell that used to
        # source this file. Read as words, `# old: ELM_ALLOWED_PROVIDERS=anthropic`
        # set the variable and let `--model anthropic/...` through, and
        # `# the install's settings` was an unclosed quote that stopped every start.
        tokens = shlex.split(text, comments=True)
    except ValueError as problem:
        raise Refusal("elm-pi runtime configuration is unreadable: %s" % problem,
                      "    Run %s to write it again." % os.path.join(root, "bootstrap.sh"),
                      code=CANNOT_START)
    for token in tokens:
        if token == "export":
            continue
        name, separator, value = token.partition("=")
        if separator and NAME.match(name):
            env.set(name, value)


def credential_names(root):
    """The provider credential list, read from config/elm-pi.json.

    The `--help` path uses this when runtime.env has not been written yet: an
    install that cannot start is exactly the one whose help you want to read,
    and pi's half of it must not run with a stray commercial key either.
    """
    try:
        with open(os.path.join(root, "config", "elm-pi.json"),
                  encoding="utf-8", errors="replace") as handle:
            return list(json.load(handle).get("providerCredentials", []))
    except (OSError, ValueError):
        return []
