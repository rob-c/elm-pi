"""Which model strings elm-pi's three model gates let through, as generated
matrices over the three ELM models (config/elm-pi.json "models").

Three pieces of code decide which model a run, or an agent inside it, may use:

1. lib/policy.sh, elm_policy_check_args: the launcher's argument guard. A bare
   model id passes only when it is one this install serves, in any case and
   with surrounding whitespace (Mistral's only when runtime.env names it);
   anything else must name an allowed provider (elm, elm-shim) before its first
   slash. The guard checks the provider, not which ids that provider serves.
2. templates/extensions/workflow-model-scope.ts, decide(): a workflow agent's
   provider/id must be one of the three served pairs, elm/<qwen>,
   elm-shim/<llama> or elm/<mistral>. Case, a :thinking suffix and surrounding
   whitespace do not matter, and neither does where the model came from. The
   crossed pairs (elm/<llama>, elm-shim/<qwen>, elm-shim/<mistral>) are refused.
3. ./pi, --llama and --mistral: each puts --model elm-shim/<llama> or
   elm/<mistral> in front of pi's arguments unless the caller already chose a
   model, whatever other launcher flags come with it and in whichever order.
   Given together they are refused (exit 2). After -- or as the value of an
   option that takes one, either flag is text.

tests/test_policy.py, tests/test_launcher_cases.py (GuardTests,
LauncherFlagTests) and tests/test_policy_extensions.py (WorkflowModelScopeTests)
cover each gate with hand-picked cases. Here each model is crossed with the
spellings, the ways of passing a model, the environment and the other launcher
flags, and the combinations those files already have are left out. Expected
answers come from the rules above, not from a run. Each table runs in one
process (one bash per launcher table, one node for the extension) using those
files' runners, and each case is its own test method. A case marked bug is an
expected failure: it states the rule and the code does not yet keep it.
"""

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_launcher_cases as launcher  # noqa: E402
import test_policy_extensions as extensions  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
QWEN = CONFIG["models"]["qwen"]
LLAMA = CONFIG["models"]["llama"]
MISTRAL = CONFIG["models"]["mistral"]
C = launcher.Case


# ------------------------------------------- 1. the argument guard (lib/policy.sh)

# As GuardTests spells them (its module later reuses the name M for a helper).
M = 'model "{}" is outside the allowed providers.'
MP = 'model pattern "{}" is outside the allowed providers.'

# (name, id, its runtime.env variable, the provider that serves it)
GUARD_MODELS = (
    ("qwen", QWEN, "ELM_QWEN_MODEL_ID", "elm"),
    ("llama", LLAMA, "ELM_LLAMA_MODEL_ID", "elm-shim"),
    ("mistral", MISTRAL, "ELM_MISTRAL_MODEL_ID", "elm"),
)

# name: (spelling of a model id, allowed with every id set). A bare id is
# compared whole after trimming and lower-casing, so a thinking level, a cut or
# a suffix makes it a provider-less name; with a provider in front, only the
# provider is checked.
SPELLINGS = {
    "as_is": (lambda i: i, True),
    "upper_case": (str.upper, True),
    "lower_case": (str.lower, True),
    "padded": (lambda i: f" \t{i}  \n", True),
    "tab_padded": (lambda i: f"\t {i} \t", True),
    "on_elm": (lambda i: f"elm/{i}", True),
    "on_elm_shim": (lambda i: f"elm-shim/{i}", True),
    "bare_with_a_thinking_level": (lambda i: f"{i}:high", False),
    "on_elm_with_a_thinking_level": (lambda i: f"elm/{i}:high", True),
    "truncated": (lambda i: i[:-1], False),
    "with_a_suffix": (lambda i: f"{i}-v2", False),
    "on_a_lookalike_provider": (lambda i: f"elmx/{i}", False),
    "on_an_empty_provider": (lambda i: f"/{i}", False),
}
MODEL_OPTION_SPELLINGS = [s for s in SPELLINGS if s != "tab_padded"]
# Already cases in tests/test_policy.py or GuardTests, as --model <value>.
GUARD_EXISTING = {("qwen", "as_is"), ("llama", "as_is"), ("qwen", "lower_case"),
                  ("llama", "bare_with_a_thinking_level"), ("mistral", "on_elm")}

# The other ways to pass a model: (name, arguments for a value, message,
# a spelling that passes, one that does not). The --models forms report the
# refused pattern trimmed; the --model forms report the value as given.
FORMS = (
    ("model_equals", lambda v: [f"--model={v}"], M, "upper_case", "with_a_suffix"),
    ("short_m", lambda v: ["-m", v], M, "tab_padded", "truncated"),
    ("attached_short_m", lambda v: ["-m" + v], M, "lower_case", "bare_with_a_thinking_level"),
    ("models", lambda v: ["--models", v], MP, "on_elm_with_a_thinking_level", "on_a_lookalike_provider"),
    ("models_list", lambda v: [f"--models=elm/*, {v} ,elm-shim/*"], MP, "as_is", "on_an_empty_provider"),
)



def verdict(allowed, message, value):
    return "ALLOW" if allowed else "DENY:" + message.format(value)


GUARD_CASES = []
for name, model_id, _, _ in GUARD_MODELS:
    for spelling in MODEL_OPTION_SPELLINGS:
        if (name, spelling) in GUARD_EXISTING:
            continue
        spell, allowed = SPELLINGS[spelling]
        value = spell(model_id)
        GUARD_CASES.append(C(f"{name}_{spelling}_as_model", ["--model", value], verdict=verdict(allowed, M, value)))
    for form, build, message, good, bad in FORMS:
        for spelling in (good, bad):
            spell, allowed = SPELLINGS[spelling]
            value = spell(model_id)
            shown = value.strip() if message == MP else value
            GUARD_CASES.append(C(f"{name}_{spelling}_as_{form}", build(value),
                                 verdict=verdict(allowed, message, shown)))

# A bare id passes only while runtime.env names it; with a provider in front
# the id does not matter. Unset is a runtime.env from before the model was
# served; empty is one that names it with nothing.
for name, model_id, var, provider in GUARD_MODELS:
    for state, value in (("unset", None), ("empty", "")):
        env = {var: value}
        if state == "unset":
            GUARD_CASES.append(C(f"{name}_bare_id_as_model_refused_when_its_id_is_unset", ["--model", model_id],
                                 env=env, verdict="DENY:" + M.format(model_id)))
            GUARD_CASES.append(C(f"{name}_on_{provider}_as_model_allowed_when_its_id_is_unset",
                                 ["--model", f"{provider}/{model_id}"], env=env, verdict="ALLOW"))
        else:
            GUARD_CASES.append(C(f"{name}_bare_id_in_a_models_list_refused_when_its_id_is_empty",
                                 ["--models", f"elm/*,{model_id}"], env=env, verdict="DENY:" + MP.format(model_id)))
            GUARD_CASES.append(C(f"{name}_on_{provider}_in_a_models_list_allowed_when_its_id_is_empty",
                                 ["--models", f"{provider}/{model_id.lower()}"], env=env, verdict="ALLOW"))

# A blank model is no model's id, whichever ids runtime.env names. Was a bug: with the
# Qwen or Llama id unset or empty, a blank --model matched it and was allowed.
for name, args, env, bug in (
    ("every_id_set", ["--model", "   "], {}, None),
    ("the_mistral_id_unset", ["--model", "   "], {"ELM_MISTRAL_MODEL_ID": None}, None),
    ("the_qwen_id_unset", ["--model", "   "], {"ELM_QWEN_MODEL_ID": None}, None),
    ("the_llama_id_empty", ["--model", " \t "], {"ELM_LLAMA_MODEL_ID": ""}, None),
):
    GUARD_CASES.append(C(f"blank_model_refused_with_{name}", args, env=env, bug=bug,
                         verdict="DENY:" + M.format(args[1])))


@launcher.generate
class ArgumentGuardMatrixTests(launcher.BatchTest):
    """elm_policy_check_args over model x spelling x option form x runtime.env."""

    CASES = tuple(GUARD_CASES)

    @classmethod
    def prelude(cls):
        return f". {launcher.q(ROOT / 'lib/policy.sh')}"

    @classmethod
    def body(cls, case):
        env = {"ELM_ALLOWED_PROVIDERS": "elm elm-shim", "ELM_QWEN_MODEL_ID": QWEN, "ELM_LLAMA_MODEL_ID": LLAMA,
               "ELM_MISTRAL_MODEL_ID": MISTRAL, **case.env}
        return "\n".join([launcher.exports(env), launcher.setargs(case.args),
                          'if elm_policy_check_args "$@"; then V=ALLOW; else V="DENY:$ELM_POLICY_ERROR"; fi',
                          "_v V"])

    def check(self, case, r):
        self.assertEqual(0, r.rc, r.err)
        self.assertEqual(case.kw["verdict"], r.vars.get("V"), case.args)


# ------------------------------- 2. workflow agents (workflow-model-scope.ts)

AGENT_DIR = extensions.AGENT_DIR
COMMERCIAL = "openai/gpt-5"
SERVED_QWEN = f"elm/{QWEN}"

# (provider, model name, id, served)
SCOPE_SPECS = (
    ("elm", "qwen", QWEN, True),
    ("elm_shim", "llama", LLAMA, True),
    ("elm", "mistral", MISTRAL, True),
    ("elm", "llama", LLAMA, False),
    ("elm_shim", "qwen", QWEN, False),
    ("elm_shim", "mistral", MISTRAL, False),
)
SCOPE_CASE_FORMS = (("as_given", lambda s: s), ("upper", str.upper), ("lower", str.lower),
                    ("swapped_case", str.swapcase))
SCOPE_LEVELS = (("no_level", ""), ("off", ":off"), ("high", ":high"), ("thinking", ":thinking"))
SCOPE_SPACES = (("bare", "", ""), ("padded", " \n", "  "), ("tab_padded", "\t", " \t"))
SOURCES = ("explicit", "tier", "phase")


def scope_ctx(model, source, resolved, decoy):
    """The model as requested, or as resolved with a decoy requested that would
    be judged the other way: resolvedModel is what the package spawns."""
    ctx = {"modelSource": source}
    if source == "tier":
        ctx["tier"] = "fast"
    if resolved:
        ctx.update(requestedModel=decoy, resolvedModel=model)
    else:
        ctx["requestedModel"] = model
    return ctx


def where(source):
    return {"explicit": "an explicit model on the script or agent type",
            "tier": f'the "fast" tier in {AGENT_DIR}/workflows/model-tiers.json',
            "phase": "a workflow phase or meta model"}[source]


# Eight cases per spec: every case form and thinking level twice, every
# whitespace and source at least twice, half of them as the resolved model.
SCOPE_CASES = []
for j, (provider, name, model_id, served) in enumerate(SCOPE_SPECS):
    for i in range(8):
        form_name, form = SCOPE_CASE_FORMS[i % 4]
        level_name, level = SCOPE_LEVELS[(i + i // 4 + j) % 4]
        space_name, before, after = SCOPE_SPACES[(i + j + 1) % 3]
        source = SOURCES[(i + 2 * j) % 3]
        resolved = (i + j) % 2 == 1
        model = before + form(f"{provider.replace('_', '-')}/{model_id}") + level + after
        case_id = (f"{'served' if served else 'crossed'}_{provider}_{name}_{form_name}_{level_name}_{space_name}"
                   f"_{source}{'_resolved' if resolved else '_requested'}")
        ctx = scope_ctx(model, source, resolved, COMMERCIAL if served else SERVED_QWEN)
        SCOPE_CASES.append(extensions.ok(case_id, ctx) if served else extensions.unserved(case_id, ctx))

# Near misses keep failing with a thinking level on: the level is stripped
# before the id is compared, not instead of comparing it.
for k, (provider, name, model_id, _) in enumerate(SCOPE_SPECS[:3]):
    spec_provider = provider.replace("_", "-")
    source = SOURCES[(k + 1) % 3]
    SCOPE_CASES.append(extensions.unserved(
        f"truncated_{name}_with_a_level_is_unserved_{source}",
        scope_ctx(f"{spec_provider}/{model_id[:-1]}:high", source, False, None)))
    SCOPE_CASES.append(extensions.offsite(
        f"bare_{name}_id_with_a_level_is_offsite_{source}",
        scope_ctx(f"{model_id}:off", source, False, None), where(source)))

_existing = {json.dumps(c["ctx"], sort_keys=True) for c in extensions.SCOPE_CASES + extensions.SCOPE_UNLOCKED_CASES}
_dupes = [c["id"] for c in SCOPE_CASES if json.dumps(c["ctx"], sort_keys=True) in _existing]
if _dupes:
    raise RuntimeError(f"already in tests/test_policy_extensions.py: {_dupes}")


class WorkflowScopeMatrixTests(unittest.TestCase):
    """decide() over served and crossed specs x case x thinking level x
    whitespace x model source x requested or resolved."""

    @classmethod
    def setUpClass(cls):
        env = {"ELM_QWEN_MODEL_ID": QWEN, "ELM_LLAMA_MODEL_ID": LLAMA, "ELM_MISTRAL_MODEL_ID": MISTRAL}
        cls.out = extensions.run_extension("workflow-model-scope.ts", extensions.SCOPE_RUNNER, {"configs": [
            {"id": "matrix", "env": env,
             "cases": [{"id": c["id"], "ctx": c["ctx"], "agentDir": c.get("agentDir")} for c in SCOPE_CASES]},
        ]})

    def check(self, case):
        self.assertEqual(case["expect"], self.out[case["id"]], case["ctx"])


extensions.generate(WorkflowScopeMatrixTests, SCOPE_CASES, WorkflowScopeMatrixTests.check)


# --------------------------------------------- 3. the launcher's --llama/--mistral

# What the LauncherFlagTests prelude puts in runtime.env's place.
FLAG_MODEL = {"--llama": ["--model", f"elm-shim/{launcher.LLAMA}"],
              "--mistral": ["--model", f"elm/{launcher.MISTRAL}"]}
ALWAYS, WEB, WF, DEFAULT_XT = launcher.ALWAYS, launcher.WEB, launcher.WF, launcher.DEFAULT_XT
xt, ext = launcher.xt, launcher.ext
REFUSED = "--llama and --mistral each choose the model for the run; give one of them."
NO_MISTRAL = "--mistral needs this install's Mistral model id"


def picks(flag, on=True):
    return {"LLAMA": "1" if on and flag == "--llama" else "0",
            "MISTRAL": "1" if on and flag == "--mistral" else "0"}


def pre(first, model, rest_of_pre):
    """first(h) + the flag's --model, if any + the rest, as LauncherFlagTests compares PRE."""
    return lambda h: first(h) + model + rest_of_pre


def nothing(h):
    return []


# The other launcher flags (and -ne, which is pi's but changes PRE): name,
# token, whether the launcher takes it out of pi's arguments, the variables it
# sets, what it puts in PRE before the model (given whether the shim is
# wanted), its tool exclusion, and the model choice paired with it.
OTHERS = (
    ("fast", "--fast", True, {"FAST": "1"},
     lambda shim: lambda h: launcher.fastpre(h) + (ext(h, "elm-shim") if shim else []),
     xt(DEFAULT_XT), ["--provider", "elm-shim"]),
    ("remote", "--remote", True, {"REMOTE": "1", "PI_ELM_WEB": "1"}, lambda shim: launcher.cu,
     xt(ALWAYS), ["--model", "elm/q"]),
    ("workflows", "--workflows", True, {"WORKFLOWS": "1"}, lambda shim: nothing,
     xt(ALWAYS), ["--model=elm/q"]),
    ("no_workflows", "--no-workflows", True, {"WORKFLOWS": "0"}, lambda shim: nothing,
     xt(ALWAYS, WF), ["--model=elm/q"]),
    ("with_all", "--with-all", True, {"WITH_ALL": "1", "WORKFLOWS": "1"}, lambda shim: nothing,
     [], ["--provider", "elm"]),
    ("mode", None, True, {}, lambda shim: nothing, xt(DEFAULT_XT), ["--model", "elm-shim/q"]),
    ("ne", "-ne", False, {"FAST": "0"}, lambda shim: lambda h: ext(h, *launcher.POLICY) + launcher.gate(h),
     xt(DEFAULT_XT), ["--model=elm/q"]),
)
# The three permission-mode flags take turns as the "mode" flag.
MODE_TURNS = {("--llama", True): "--manual", ("--llama", False): "--auto",
              ("--mistral", True): "--yolo", ("--mistral", False): "--manual"}

FLAG_CASES = []
for flag in ("--llama", "--mistral"):
    for flag_first in (True, False):
        for other, token, launchers, sets, first, xt_args, choice in OTHERS:
            if other == "mode":
                token = MODE_TURNS[(flag, flag_first)]
                sets = {"MODE_FLAG": token[2:]}
                other = token[2:]
            kept = [] if launchers else [token]
            for chosen in ([], choice):
                if flag_first:
                    args, rest = [flag, token, *chosen, "-p", "x"], [*kept, *chosen, "-p", "x"]
                else:
                    args, rest = ["-p", "x", *chosen, token, flag], ["-p", "x", *chosen, *kept]
                shim = flag == "--llama" or any("elm-shim" in a for a in chosen)
                model = [] if chosen else FLAG_MODEL[flag]
                FLAG_CASES.append(C(
                    f"routing_{flag[2:]}_{'before' if flag_first else 'after'}_{other}"
                    f"_{'with_' + re.sub(r'[^a-z]+', '_', ' '.join(chosen)).strip('_') if chosen else 'no_model'}",
                    args, vars={**picks(flag), **sets},
                    # --yolo is the network yolo too, so computer use loads exactly
                    # as it does with --remote (the mode is one decision).
                    pre=(lambda h, f=pre(first(shim), model, xt_args): launcher.cu(h) + f(h))
                    if "--yolo" in args else pre(first(shim), model, xt_args), rest=rest))

# Text, not the launcher's flag: after --, or as the value of an option pi
# reads whatever follows. -p and --name -- do not make it text: pi's -p never
# takes a value that starts with "-", and a -- that is --name's value does not
# end pi's options.
VALUE_OPTIONS = ("--append-system-prompt", "--system-prompt", "-n", "--thinking")
for flag in ("--llama", "--mistral"):
    name = flag[2:]
    plain = launcher.fixed(xt(DEFAULT_XT))
    flagged = launcher.fixed(FLAG_MODEL[flag] + xt(DEFAULT_XT))
    FLAG_CASES.append(C(f"routing_{name}_after_double_dash_with_a_prompt_is_text", ["-p", "x", "--", flag],
                        vars=picks(flag, False), pre=plain, rest=["-p", "x", "--", flag]))
    for option in VALUE_OPTIONS:
        if (flag, option) == ("--mistral", "--append-system-prompt"):
            continue  # LauncherFlagTests: mistral_as_an_options_value_is_text
        FLAG_CASES.append(C(f"routing_{name}_as_the_value_of_{option.strip('-').replace('-', '_')}_is_text",
                            [option, flag, "-p", "x"], vars=picks(flag, False), pre=plain,
                            rest=[option, flag, "-p", "x"]))
    FLAG_CASES.append(C(f"routing_{name}_after_a_double_dash_name_value_is_the_launchers",
                        ["--name", "--", flag, "-p", "x"], vars=picks(flag), pre=flagged,
                        rest=["--name", "--", "-p", "x"]))
    FLAG_CASES.append(C(f"routing_{name}_after_print_is_the_launchers", ["-p", flag], vars=picks(flag),
                        pre=flagged, rest=["-p"]))
    # A --model the caller did not give to pi does not count as choosing one.
    value_option = "--append-system-prompt" if flag == "--llama" else "-n"
    for label, args, chosen in (
        ("model_after_double_dash_is_not_a_choice", [flag, "-p", "--", "--model", "elm/q"], False),
        (f"model_as_the_value_of_{value_option.strip('-').replace('-', '_')}_is_not_a_choice",
         [flag, value_option, "--model", "elm/q"], False),
        ("model_after_a_double_dash_name_value_is_a_choice", [flag, "--name", "--", "--model", "elm/q"], True),
        ("models_scope_is_not_a_model_choice", [flag, "--models", "elm/q"], False),
    ):
        FLAG_CASES.append(C(f"routing_{name}_{label}", args, vars=picks(flag),
                            pre=plain if chosen else flagged, rest=args[1:]))

# --mistral needs runtime.env to name Mistral, however it is given; --llama and
# a --mistral that is text do not.
FLAG_CASES += [
    C("routing_mistral_refused_when_runtime_env_lacks_the_id", ["--mistral", "-p", "x"],
      env={"ELM_MISTRAL_MODEL_ID": None}, rc=1, err_has=[NO_MISTRAL, "bootstrap.sh"]),
    C("routing_mistral_with_a_model_still_needs_the_id", ["--mistral", "--model", "elm/q"],
      env={"ELM_MISTRAL_MODEL_ID": ""}, rc=1, err_has=NO_MISTRAL),
    C("routing_mistral_as_text_does_not_need_the_id", ["-p", "x", "--", "--mistral"],
      env={"ELM_MISTRAL_MODEL_ID": ""}, vars=picks("--mistral", False), pre=launcher.fixed(xt(DEFAULT_XT)),
      rest=["-p", "x", "--", "--mistral"], err_lacks=NO_MISTRAL),
    C("routing_llama_does_not_need_the_mistral_id", ["--llama", "-p", "x"],
      env={"ELM_MISTRAL_MODEL_ID": ""}, vars=picks("--llama"),
      pre=launcher.fixed(FLAG_MODEL["--llama"] + xt(DEFAULT_XT)), rest=["-p", "x"], err_lacks=NO_MISTRAL),
]

# Both flags: refused wherever the second one is still the launcher's, before
# any other flag has done anything; when the second is text, the first picks.
for first_flag, second_flag in (("--llama", "--mistral"), ("--mistral", "--llama")):
    a, b = first_flag[2:], second_flag[2:]
    between = "--remote" if first_flag == "--llama" else "--yolo"
    option = "--append-system-prompt" if first_flag == "--llama" else "-n"
    for label, args in (
        (f"with_{between[2:]}_between", [first_flag, between, second_flag]),
        ("with_a_model_between", [first_flag, "--model", "elm/q", second_flag]),
        ("after_print", [first_flag, "-p", second_flag]),
        ("after_a_double_dash_name_value", [first_flag, "--name", "--", second_flag]),
    ):
        FLAG_CASES.append(C(f"routing_{a}_then_{b}_{label}_is_refused", args, rc=2, err_has=REFUSED,
                            err_lacks="web tools on"))
    for label, args in (
        ("after_double_dash", [first_flag, "-p", "x", "--", second_flag]),
        (f"as_the_value_of_{option.strip('-').replace('-', '_')}", [first_flag, option, second_flag]),
    ):
        FLAG_CASES.append(C(f"routing_{a}_then_{b}_{label}_picks_{a}", args, vars=picks(first_flag),
                            pre=launcher.fixed(FLAG_MODEL[first_flag] + xt(DEFAULT_XT)), rest=args[1:],
                            err_lacks=REFUSED))


class ModelFlagMatrixTests(launcher.LauncherFlagTests):
    """--llama/--mistral x the other launcher flags x order x a model the caller
    chose, as text, and together, through LauncherFlagTests' blocks of ./pi."""

    CASES = tuple(FLAG_CASES)


# The parent's own cases run in LauncherFlagTests; this class runs only its own.
for _name in [n for n in dir(launcher.LauncherFlagTests) if n.startswith("test_")]:
    setattr(ModelFlagMatrixTests, _name, None)
launcher.generate(ModelFlagMatrixTests)


if __name__ == "__main__":
    unittest.main()
