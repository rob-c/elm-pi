"""The values this repo owns inside agent/: reapplied, and reported.

agent/ is yours to tune, with one exception: some values are decisions this
repo makes, usually for a measured or documented reason, and a re-install has
to be able to change its mind about them. Worktree isolation is the worked
example - it went on, then came back off once it proved to need a git
repository - and install_if_absent would have kept the stale `true` on every
existing install for ever.

So every run compares the live files against templates/, prints anything you
have changed, and then applies the repo's decision over the top. Nothing is
overwritten silently. Every other key - theme, model, concurrency, search
routing, your own additions - is left exactly as it is. To change a decision
permanently, change templates/, not agent/.

This is bootstrap.sh's embedded Python, moved here as it was: the merge, the
models.json rules (Qwen's and Mistral's per-model keys, the one Llama that
cannot call tools), the hashline and workflow settings, the package list, and
the record of what is installed.
"""

import collections
import json
import os

# The phase headings ("installer-owned settings", "workflow settings") are the
# runner's, as they are bootstrap.sh's `say` lines beside these heredocs; what
# is here is what the heredocs printed.

# file -> the keys this repo decides. The reason for each is in the file it
# belongs to (templates/), or in bootstrap.sh's notes beside this list.
OWNED = {
    "settings.json": (
        "extensions",            # where local extensions are discovered
        "compaction",            # off: pi-auto-compact owns compaction
        "subagents",             # model tiering, fallbacks, ELM-only modelScope
        "sessionDir",            # per-project .pi/sessions, not one central pile
        "defaultThinkingLevel",  # off: measured ~400x slower here for no gain
        "retry",                 # gateway retry policy
        "httpIdleTimeoutMs",     # 120s: a silent request is retried sooner
        "defaultProjectTrust",   # never: a repo's .pi/ cannot load code or
                                 # override settings unless /trust says so
        "shellCommandPrefix",    # agent/shell/colour.sh: colour for output
                                 # that goes straight back to pi
    ),
    "extensions/subagent/config.json": (
        "globalConcurrencyLimit",  # 12: measured on the gateway; more meets
                                   # the rate limit every ELM user shares
        "share",                 # false: `gh gist create` publishes a run
        "worktree",              # false: isolation needs git, so it is opt-in
        "worktreeProvider",
        "worktreeBaseDir",
        "maxSubagentSpawnsPerRun",
        "disabledFeatures",      # agent-management: the model cannot enable,
                                 # create or edit agents through the tool
    ),
    "extensions/pi-permission-system/config.json": (
        "permission",            # the gate: outside-cwd, secrets, bash
        "piInfrastructureReadPaths",
    ),
    "config/pi-task-models/config.json": (
        "profiles",              # frontier/balanced/fast -> Qwen+think, Qwen,
                                 # Mistral+think; Mistral is the fallback too
        "tasks",                 # compaction routed to balanced
    ),
    "config/pi-auto-compact/config.json": (
        "autoCompactThreshold",  # 70: each compaction re-sends the history
                                 # uncached, so compacting early costs more
                                 # than the context it frees
    ),
    "web-search.json": (
        "pdf",                   # provider unpdf: keeps PDFs off Datalab/Gemini
    ),
}


def _as_json(text):
    """A value pasted into JSON text has to be escaped first."""
    return json.dumps(text)[1:-1]


def _load(root, path, model_ids=None):
    """A JSON file as templates/ means it: model tokens and install paths in it."""
    with open(path, encoding="utf-8") as handle:
        raw = handle.read()
    if model_ids is not None:
        raw = raw.replace("@QWEN_MODEL@", _as_json(model_ids["qwen"]))
        raw = raw.replace("@LLAMA_MODEL@", _as_json(model_ids["llama"]))
        if "mistral" in model_ids:
            raw = raw.replace("@MISTRAL_MODEL@", _as_json(model_ids["mistral"]))
    return json.loads(raw, object_pairs_hook=collections.OrderedDict)


def _same(a, b):
    """Equal as JSON is: 0 is not False, 70.0 is still 70, key order is free."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _brief(value):
    """The report format: the JSON, cut to 57 characters and "..." past 60."""
    text = json.dumps(value)
    return text if len(text) <= 60 else text[:57] + "..."


def _model_ids(root):
    """The config's ids under the recorded ones, as scripts/elm_config.py reads them.

    A model added to config/elm-pi.json after this install recorded its ids is
    still known.
    """
    ids = {}
    config = os.path.join(root, "config", "elm-pi.json")
    if os.path.exists(config):
        with open(config, encoding="utf-8") as handle:
            ids = dict(json.load(handle)["models"])
    ids.update(_load(root, os.path.join(root, "agent", "model-ids.json")))
    return ids


def merge_owned(root):
    """Reapply this repo's keys over yours, and say what changed."""
    model_ids = _model_ids(root)
    for relative, keys in OWNED.items():
        template = os.path.join(root, "templates", relative)
        live = os.path.join(root, "agent", relative)
        if not (os.path.exists(template) and os.path.exists(live)):
            continue
        wanted, current = _load(root, template, model_ids), _load(root, live, model_ids)
        changed = []
        for key in keys:
            if key not in wanted:
                continue
            raw = json.dumps(wanted[key])
            raw = raw.replace("@AGENT_DIR@", _as_json(os.path.join(root, "agent")))
            raw = raw.replace("@INSTALL_DIR@", _as_json(root))
            value = json.loads(raw)
            if not _same(current.get(key), value):
                changed.append((key, current.get(key), value))
                current[key] = value
        if changed:
            with open(live, "w", encoding="utf-8") as handle:
                json.dump(current, handle, indent=2)
                handle.write("\n")
            print("    agent/" + relative)
            for key, was, now in changed:
                print("      %s: yours %s -> repo %s" % (key, _brief(was), _brief(now)))
        else:
            print("    agent/%s matches" % relative)
    models(root, model_ids)


def models(root, model_ids=None):
    """models.json is not a key merge: configure.sh resolves the Qwen id, so the
    ids are live data.

    The decisions here are that exactly one Llama exists - the shim one, since
    `configure.sh llama` re-adds a direct ELM entry that cannot call tools at
    all - and that Mistral is listed: an install made before ELM served it has
    no entry, and is given the template's.
    """
    model_ids = model_ids if model_ids is not None else _model_ids(root)
    path = os.path.join(root, "agent", "models.json")
    if not os.path.exists(path):
        return
    data = _load(root, path, model_ids)
    elm = data.get("providers", {}).get("elm", {})
    dirty = False
    template = _load(root, os.path.join(root, "templates", "models.json"), model_ids)
    template_qwen = template["providers"]["elm"]["models"][0]

    # Three per-model keys are this repo's decisions, reapplied to the live Qwen
    # entry on every run because configure.sh preserves them:
    #   samplingParams                 the Qwen3.5 card's Instruct (non-thinking)
    #                                  profile, presence_penalty 1.5 included,
    #                                  against repetition loops, and
    #                                  repetition_penalty 1.0 said rather than
    #                                  left to the server's default
    #   samplingParamsByThinkingLevel  the card's thinking-mode profile
    #                                  (presence_penalty 0, repetition_penalty 1.0)
    #   compat                         how the gateway takes the thinking switch:
    #                                  pi 1.4.0 dropped the whole elm provider
    #                                  over a thinkingFormat it stopped accepting
    for model in elm.get("models", []):
        if "qwen" not in model.get("id", "").lower():
            continue
        for key in ("samplingParams", "samplingParamsByThinkingLevel", "compat"):
            if key in template_qwen and not _same(model.get(key), template_qwen[key]):
                print("    agent/models.json: %s %s -> %s"
                      % (key, json.dumps(model.get(key)), json.dumps(template_qwen[key])))
                model[key] = template_qwen[key]
                dirty = True

    # maxTokens is yours to tune, so it is left alone - except the 32768 every
    # install before this one was given, which was a guess and not ELM's limit.
    old_max_tokens = 32768
    for model in elm.get("models", []):
        wanted = next((t for t in template["providers"]["elm"]["models"]
                       if t.get("id", "").lower() == model.get("id", "").lower()), None)
        if (wanted is None or model.get("maxTokens") != old_max_tokens
                or wanted.get("maxTokens") in (None, old_max_tokens)):
            continue
        print("    agent/models.json: maxTokens of elm/%s %d -> %d"
              % (model["id"], old_max_tokens, wanted["maxTokens"]))
        model["maxTokens"] = wanted["maxTokens"]
        dirty = True

    # Mistral's three keys are reapplied the same way:
    #   compat                         pi sends a reasoning model's system prompt
    #                                  as "developer" unless told not to, and
    #                                  ELM's Mistral answers that with a 400
    #   samplingParams                 0.15: the model ships no defaults, so vLLM
    #                                  samples at 1.0; measured 38/51 against
    #                                  33/51 at the default
    #   samplingParamsByThinkingLevel  0.7 with reasoning on
    mistral_id = model_ids.get("mistral", "")
    template_mistral = next((m for m in template["providers"]["elm"]["models"]
                             if mistral_id and m.get("id", "").lower() == mistral_id.lower()),
                            None)
    if template_mistral is not None:
        mine = [m for m in elm.get("models", []) if m.get("id", "").lower() == mistral_id.lower()]
        for model in mine:
            for key in ("compat", "samplingParams", "samplingParamsByThinkingLevel"):
                if key in template_mistral and not _same(model.get(key), template_mistral[key]):
                    print("    agent/models.json: %s %s -> %s"
                          % (key, json.dumps(model.get(key)), json.dumps(template_mistral[key])))
                    model[key] = template_mistral[key]
                    dirty = True
        if not mine and "models" in elm:
            elm["models"].append(template_mistral)
            print("    agent/models.json: added elm/%s" % mistral_id)
            dirty = True

        # Mistral thinks by default: with reasoning_effort high it passed 46 of
        # 51 small agent tasks against 38 without. modelThinkingLevels is yours,
        # so an install only gets the entry when it has none for Mistral.
        settings_path = os.path.join(root, "agent", "settings.json")
        if os.path.exists(settings_path):
            live_settings = _load(root, settings_path, model_ids)
            levels = live_settings.get("modelThinkingLevels")
            key = "elm/" + mistral_id
            if isinstance(levels, dict) and not any(k.lower() == key.lower() for k in levels):
                levels[key] = "high"
                with open(settings_path, "w", encoding="utf-8") as handle:
                    json.dump(live_settings, handle, indent=2)
                    handle.write("\n")
                print("    agent/settings.json: modelThinkingLevels %s -> high" % key)

    strays = [m for m in elm.get("models", []) if "llama" in m.get("id", "").lower()]
    if strays or dirty:
        elm["models"] = [m for m in elm.get("models", []) if m not in strays]
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        for model in strays:
            print("    agent/models.json: removed elm/%s - it cannot call tools;" % model.get("id"))
            print("      the shim entry elm-shim/meta-llama/... is the supported one")
    else:
        print("    agent/models.json matches")


def hashline(root):
    """pi-hashline-edit-pro's settings: requirePath on, copy and move off.

    requirePath makes every anchor edit name its file, which lets
    protected-paths.ts check it; a move's destination comes from an anchor, not
    from the path it names.
    """
    os.makedirs(os.path.join(root, "agent", "hashline"), exist_ok=True)
    with open(os.path.join(root, "templates", "hashline", "config.json"),
              encoding="utf-8") as handle:
        want = json.load(handle)
    path = os.path.join(root, "agent", "hashline", "config.json")
    live = None
    try:
        with open(path, encoding="utf-8") as handle:
            live = json.load(handle)
    except OSError:
        live = {}
    except ValueError:
        live = None
    if not isinstance(live, dict):
        print("    agent/hashline/config.json was not a JSON object - replaced")
        live = {}
    changed = sorted(k for k, v in want.items() if live.get(k) != v)
    live.update(want)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(live, handle, indent=2)
        handle.write("\n")
    print("    agent/hashline/config.json: " + ("set " + ", ".join(changed) if changed
                                               else "matches"))


def workflow(root):
    """pi-dynamic-workflows' settings, which the package reads from agent/.

    inheritMainModel: an agent with no model runs on the session model, which is
    ELM. keywordTriggerEnabled false: otherwise any message containing the word
    "workflow" forces a fan-out. providerMiddlewareExtensions: workflow children
    load no extensions by default - no permission gate, no protected paths - so
    the policy and the within-session guards are loaded into them. A live probe
    (2026-11-13) had a workflow agent given six steps make no tool call and
    report six made-up results, twice.
    """
    with open(os.path.join(root, "templates", "workflows", "settings.json"),
              encoding="utf-8") as handle:
        want = json.load(handle)
    path = os.path.join(root, "agent", "workflows", "settings.json")
    try:
        with open(path, encoding="utf-8") as handle:
            live = json.load(handle)
    except OSError:
        live = {}
    except ValueError:
        live = None
    if not isinstance(live, dict):
        print("    %s was not a JSON object - replaced" % path)
        live = {}
    changed = {k: v for k, v in want.items() if live.get(k) != v}
    if changed:
        live.update(want)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(live, handle, indent=2)
            handle.write("\n")
        print("    %s: set %s" % (path, ", ".join(sorted(changed))))
    else:
        print("    %s matches" % path)


def package_list(root):
    """agent/settings.json's "packages": derived from templates every run.

    Filtering the live list in place could only ever remove: an install that had
    once been run with --no-packages kept an empty list for ever after, so a
    later run installed every package into agent/npm and then loaded none of
    them. Everything else in that file is yours and is left exactly as it was.
    Returns the package names npm has to have, in order.
    """
    with open(os.path.join(root, "templates", "settings.json"), encoding="utf-8") as handle:
        chosen = json.load(handle).get("packages", [])
    path = os.path.join(root, "agent", "settings.json")
    with open(path, encoding="utf-8") as handle:
        settings = json.load(handle)
    was = settings.get("packages", [])
    settings["packages"] = chosen
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)
        handle.write("\n")

    def name(spec):
        spec = spec["source"] if isinstance(spec, dict) else spec
        # spec[4:], not removeprefix: that is 3.9+, and macOS 11's
        # /usr/bin/python3 is 3.8.
        return spec[4:] if spec.startswith("npm:") else spec

    print("    loading: " + (", ".join(name(p) for p in chosen) or "none"))
    if sorted(map(json.dumps, was)) != sorted(map(json.dumps, chosen)):
        print("    (agent/settings.json listed %d package(s); corrected to match)" % len(was))
        # Named, not counted: a package added by hand stops loading here, and
        # its files go with the next rebuild of agent/npm.
        wanted = set(name(p) for p in chosen)
        dropped = sorted(set(name(p) for p in was) - wanted)
        if dropped:
            print("    not in templates/: %s - removed. Packages come from "
                  "templates/packages.json" % ", ".join(dropped))
            print("      and templates/settings.json; add one there to keep it (CONTRIBUTING.md)")
    return [name(p) for p in chosen]


def disable_packages(root):
    """--no-packages: nothing loads, whatever the file said before."""
    path = os.path.join(root, "agent", "settings.json")
    with open(path, encoding="utf-8") as handle:
        settings = json.load(handle)
    settings["packages"] = []
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)
        handle.write("\n")
    print("    packages disabled in agent/settings.json")


def installed_versions(root):
    """Record the exact versions this install is running, after every check passes.

    In config/versions.json's format, so copying this over it is how the tested
    set moves forward (CONTRIBUTING.md).
    """

    def installed(tree, manifest):
        found = {}
        with open(os.path.join(root, manifest), encoding="utf-8") as handle:
            dependencies = json.load(handle).get("dependencies", {})
        for name in dependencies:
            meta = os.path.join(root, tree, name, "package.json")
            if os.path.exists(meta):
                with open(meta, encoding="utf-8") as handle:
                    found[name] = json.load(handle)["version"]
        return found

    record = {"core": installed("node_modules", "package.json"),
              "packages": installed("agent/npm/node_modules", "templates/packages.json")}
    with open(os.path.join(root, "agent", "installed-versions.json"), "w",
              encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")
    print("    versions: agent/installed-versions.json")
    tested = {}
    if os.path.exists(os.path.join(root, "config", "versions.json")):
        with open(os.path.join(root, "config", "versions.json"), encoding="utf-8") as handle:
            tested = json.load(handle)
    newer = ["%s %s" % (name, version) for section in record
             for name, version in record[section].items()
             if tested.get(section, {}).get(name) not in (None, version)]
    if newer:
        print("      differs from config/versions.json: " + ", ".join(newer))
