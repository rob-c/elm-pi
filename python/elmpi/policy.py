"""The ELM-only model policy, at the argument level.

Staff allocations are funded at industry token rates, which does not buy a
meaningful amount of commercial-model usage: this install offers the
university's self-hosted models only, and says so in LOCKDOWN.md.

Three layers hold that, and this module is the second:

  1. credentials.scrub() - a stray key in ~/.zshrc cannot enable a provider
  2. this guard          - --provider/--model/--api-key cannot route elsewhere
  3. agent/extensions/elm-only.ts - strips every other provider's catalogue

This is the reference launcher's `elm_policy_check_args`, decision for decision. It
is default-deny and deliberately not a list of providers known when it was
written: a provider pi adds tomorrow is refused without an edit here. The
allowlist is elm_* in runtime.env, and only the last of pi's repeated options
counts because only the last is what pi uses.
"""

from elmpi.argwalk import takes_value

# What the reference trims: POSIX [[:space:]], six ASCII characters. Python's
# bare strip() also takes U+00A0, U+001F and the rest of Unicode's whitespace,
# so `--provider "\u00a0elm"` was allowed here and refused there.
SPACE = " \t\n\r\x0b\x0c"

# pi's own package and catalogue commands are not model sessions. (`update`
# must be here: `pi update --models` passes --models as a switch, not a
# value, and refusing it as a model pattern would replace a helpful message
# with a confusing one.)
NOT_SESSIONS = frozenset({"update", "install", "remove"})

PROVIDER_ALLOWED = "provider \"%s\" is not available."
MODEL_REFUSED = "model \"%s\" is outside the allowed providers."
MODEL_PATTERN_REFUSED = "model pattern \"%s\" is outside the allowed providers."
API_KEY_REFUSED = "--api-key is disabled: it can route a session to another provider."
EXTENSION_REFUSED = ("-e/--extension is disabled: \"%s\" would run unreviewed, with this "
                     "install's access and its own network code.")


def _known_ids(env):
    """The model ids runtime.env records, lowercased: bare ids pi resolves, and
    no empty string - an unset id used to make "" a model, so a blank --model
    was allowed."""
    ids = set()
    for name in ("ELM_QWEN_MODEL_ID", "ELM_LLAMA_MODEL_ID", "ELM_MISTRAL_MODEL_ID"):
        value = env.get(name).strip(SPACE).lower()
        if value:
            ids.add(value)
    return ids


def provider_allowed(candidate, env):
    """True when `candidate` is one of this install's providers."""
    allowed = {name.lower() for name in env.get("ELM_ALLOWED_PROVIDERS", "elm elm-shim").split()}
    return candidate.strip(SPACE).lower() in allowed


def model_allowed(candidate, env):
    """A bare model id this install serves, or `provider/id` with an allowed
    provider. Everything else - including a bare id of some other provider's -
    is outside the allowlist."""
    candidate = candidate.strip(SPACE)
    if candidate.lower() in _known_ids(env):
        return True
    provider, separator, _ = candidate.partition("/")
    if not separator:
        return False
    return provider_allowed(provider, env)


def _split_models(value):
    """`--models a,b` split the way pi splits it, with blanks dropped."""
    return [item.strip(SPACE) for item in value.split(",") if item.strip(SPACE)]


def check_args(argv, env):
    """The reason to refuse `argv`, or None.

    Every `-e` is refused whatever it names - pi resolves "" against the
    working folder and loads that as an extension - because an extension runs
    inside pi with this install's access and its own network code. The
    launcher's own `-e` arguments are added after this check.
    """
    if argv and argv[0] in NOT_SESSIONS:
        return None

    provider = model = models = ""
    extension = ""
    api_key = False
    extension_seen = False
    previous = ""

    for argument in argv:
        if previous == "stop":
            continue
        if previous:
            if previous == "provider":
                provider = argument
            elif previous == "model":
                model = argument
            elif previous == "models":
                models = argument
            elif previous == "api-key":
                api_key = True
            elif previous == "extension":
                extension = argument
                extension_seen = True
            previous = ""
            continue
        if argument == "--":
            previous = "stop"
        elif argument == "--provider":
            previous = "provider"
        elif argument.startswith("--provider="):
            provider = argument.split("=", 1)[1]
        elif argument in ("--model", "-m"):
            previous = "model"
        elif argument.startswith("--model=") or argument.startswith("-m="):
            model = argument.split("=", 1)[1]
        elif argument.startswith("-m") and len(argument) > 2:
            model = argument[2:]
        elif argument == "--models":
            previous = "models"
        elif argument.startswith("--models="):
            models = argument.split("=", 1)[1]
        elif argument == "--api-key":
            previous = "api-key"
        elif argument.startswith("--api-key="):
            api_key = True
        elif argument in ("-e", "--extension"):
            previous = "extension"
        elif argument.startswith("--extension=") and len(argument) > len("--extension="):
            extension = argument.split("=", 1)[1]
            extension_seen = True
        elif takes_value(argument):
            previous = "value"

    if extension_seen:
        return EXTENSION_REFUSED % extension
    if api_key:
        return API_KEY_REFUSED
    if provider and not provider_allowed(provider, env):
        return PROVIDER_ALLOWED % provider
    if model and not model_allowed(model, env):
        return MODEL_REFUSED % model
    for item in _split_models(models):
        if not model_allowed(item, env):
            return MODEL_PATTERN_REFUSED % item
    return None


__all__ = ["check_args", "model_allowed", "provider_allowed", "API_KEY_REFUSED",
           "EXTENSION_REFUSED"]
