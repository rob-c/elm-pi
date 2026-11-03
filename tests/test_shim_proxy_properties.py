"""Generated property and round-trip tests for shim/shim.py and proxy/egress.py.

The table tests in test_shim.py and test_egress_proxy.py pin chosen inputs. This
file checks the same functions against generated ones (seeded, so every run
sees the same cases, and no third-party library is needed):

shim/shim.py
- extract_call returns exactly the name and arguments of a generated call,
  however Llama wraps it: compact, spaced and ASCII-escaped, pretty-printed,
  fenced, behind <|python_tag|>, inside prose, under "parameters", or with the
  raw newlines and tabs it writes inside strings. Arguments cover every JSON
  type, nesting, unicode, escapes, braces and quotes inside strings and long
  strings, and the tool names come from generated tool lists;
- flatten_messages followed by extract_call gives back the assistant's
  tool_calls: the first from the whole message, each from its own line;
- tools_to_prompt lists every tool exactly once, with its schema intact, and
  the names it lists are names the parser accepts;
- a reply without a valid tool name never becomes a call: generated near
  misses (mutated names, wrong name types, broken JSON) and every proper
  prefix of a generated call stay prose, returned unchanged.

proxy/egress.py
- Proxy.allowed agrees with a small reference model of LOCKDOWN.md's rule,
  written independently as a label-suffix match: exact host or a subdomain of
  an entry, case-insensitive, trailing dots ignored, IP literals only in the
  spelling listed, "*" open mode. Thousands of hosts are generated per list:
  the entries, subdomains, parents, lookalikes, punycode, IPv4/IPv6 spellings;
- the verdict does not depend on the order of the list, only grows when an
  entry is added, and for a union is the "or" of the parts;
- generated CONNECT and absolute-URI request lines through Proxy.handle(): the
  host and port the proxy dials match urllib's parse of the same line, the
  origin-form line it forwards matches urllib's path and query, the verdict
  ignores the port, and every refusal is one 403 and exactly one log line.

Nothing here opens a network socket: handle() is driven with an in-memory
client, and the dial (socket.create_connection, or connect_through/splice) is
replaced, so allowed hosts are never contacted.
"""

import importlib.util
import ipaddress
import json
import os
import random
import re
import shutil
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / "shim/shim.py"
EGRESS = ROOT / "proxy/egress.py"
ELM_HOST = "elm.edina.ac.uk"
CALL_ID = re.compile(r"^call_[0-9a-f]{16}$")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


shim = load_module("elm_pi_shim_properties", SHIM)
egress = load_module("elm_pi_egress_properties", EGRESS)

CONFIG_HOSTS = json.loads((ROOT / "config/elm-pi.json").read_text())["proxyAllow"]["hosts"]
SHIPPED = [ELM_HOST] + list(CONFIG_HOSTS)


def canonical(value):
    # Order- and type-preserving: 1, 1.0, True and "1" all serialise differently.
    return json.dumps(value, ensure_ascii=False)


def slug(text):
    return re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower() or "empty"


def add_test(cls, name, fn, expected_failure=False):
    name = "test_" + name
    if name in cls.__dict__:
        raise AssertionError("duplicate generated test name %s.%s" % (cls.__name__, name))
    fn.__name__ = name
    if expected_failure:
        fn = unittest.expectedFailure(fn)
    setattr(cls, name, fn)


# =============================================================================
# generators for the shim: tool names, JSON values, calls
# =============================================================================

NAME_PARTS = ["read", "write", "edit", "bash", "ls", "grep", "fetch", "todo", "run", "mcp",
              "git", "status", "file", "x", "lire", "é", "読み", "v2", "a"]
NAME_SEPS = ["", "_", "-", ".", "__"]

# String fragments chosen to break naive parsers: braces, quotes, backslashes,
# escapes, control characters, the fence and Llama's own special tokens, and
# text that looks like a call.
FRAGMENTS = [
    "a", "path/to/file.py", "{", "}", "{{", "}}", '"', "\\", "\\n", "\n", "\t", "\r\n",
    "café", "🎉", "読み込み", "مرحبا", "\u2028", "```", "```json", "<|eot_id|>",
    "<|python_tag|>", "'", "if (x) {", "} else {", '"name": "bash"', '{"name": "read"}',
    "\x00", "\x1f", " ", "  trailing  ", "C:\\dir\\f.txt", "$HOME", "%s %d {0}",
    "\u00ff", "😀", "\udc00", "line1\nline2\n",
]
FLOATS = [0.5, -0.25, 1.0, 3.141592653589793, 1e-07, -1e300, 2.5e+20, 0.1]
INTS = [0, 1, -1, 7, 42, -42, 2 ** 31, 2 ** 63 + 1, 12345678901234567890, -10 ** 30]


def gen_name(rng):
    parts = [rng.choice(NAME_PARTS) for _ in range(rng.randint(1, 3))]
    sep = rng.choice(NAME_SEPS)
    return sep.join(parts) + (str(rng.randint(0, 99)) if rng.random() < 0.3 else "")


def gen_tool_names(rng, need):
    names = []
    while len(names) < need:
        n = gen_name(rng)
        if n not in names:
            names.append(n)
    return names


def gen_string(rng, long_ok=True):
    if long_ok and rng.random() < 0.06:
        ch = rng.choice(["x", "{", "\\", '"', "é"])
        # Kept short for "{" and '"': PrefixTests parses every prefix of a call,
        # so a long run of either makes that test quadratic, not the parser.
        return ch * (300 if ch in '{"' else rng.choice([3000, 12000]))
    return "".join(rng.choice(FRAGMENTS) for _ in range(rng.randint(0, 4)))


def gen_key(rng, name_key_ok):
    while True:
        key = rng.choice(["path", "content", "command", "name", "arguments", "parameters",
                          "", "k", "é", "{", '"', "a b", "edits"]) if rng.random() < 0.6 else gen_string(rng, False)
        if name_key_ok or key != "name":
            return key


def gen_value(rng, depth, name_key_ok=True):
    kinds = ["str", "str", "int", "float", "bool", "null"]
    if depth > 0:
        kinds += ["list", "dict", "dict"]
    kind = rng.choice(kinds)
    if kind == "str":
        return gen_string(rng)
    if kind == "int":
        return rng.choice(INTS)
    if kind == "float":
        return rng.choice(FLOATS)
    if kind == "bool":
        return rng.choice([True, False])
    if kind == "null":
        return None
    if kind == "list":
        return [gen_value(rng, depth - 1, name_key_ok) for _ in range(rng.randint(0, 4))]
    return gen_object(rng, depth - 1, name_key_ok)


def gen_object(rng, depth, name_key_ok=True):
    obj = {}
    for _ in range(rng.randint(0, 4)):
        obj[gen_key(rng, name_key_ok)] = gen_value(rng, depth, name_key_ok)
    return obj


def gen_call(seed, name_key_ok=True):
    """(tool names offered, called name, arguments) - arguments are an object,
    or occasionally an OpenAI-style JSON string the shim must pass verbatim."""
    rng = random.Random(seed)
    names = gen_tool_names(rng, rng.randint(1, 8))
    name = rng.choice(names)
    if rng.random() < 0.12:
        args = json.dumps(gen_object(rng, 2, name_key_ok), separators=(", ", " : "))
    else:
        args = gen_object(rng, rng.randint(0, 4), name_key_ok)
        # Llama writes raw newlines inside strings; make sure there is one to write.
        args[rng.choice(["content", "command", "text"])] = gen_string(rng) + "\n" + gen_string(rng)
    return names, name, args


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def raw_controls(text):
    # Replace \n and \t escapes (not escaped backslashes followed by n or t)
    # with the raw characters, as Llama writes them.
    return re.sub(r'(?<!\\)((?:\\\\)*)\\([nt])',
                  lambda m: m.group(1) + ("\n" if m.group(2) == "n" else "\t"), text)


PROSE_BEFORE = ["Let me do that now: ", "Sure.\n", "I'll call the tool.\n\n", "Calling it -\n"]
PROSE_AFTER = ["\nThat should do it.", " - done", "\n\nI will report back.", " Then I'll check."]

# (wrapper name, function of (rng, name, args) -> the model's text)
WRAPPERS = [
    ("compact", lambda r, n, a: compact({"name": n, "arguments": a})),
    ("ascii_spaced", lambda r, n, a: json.dumps({"name": n, "arguments": a})),
    ("pretty", lambda r, n, a: json.dumps({"name": n, "arguments": a}, indent=2, ensure_ascii=False)),
    ("fence_json", lambda r, n, a: "```json\n" + compact({"name": n, "arguments": a}) + "\n```"),
    ("python_tag", lambda r, n, a: "<|python_tag|>" + compact({"name": n, "parameters": a}) + "<|eom_id|>"),
    ("prose_before", lambda r, n, a: r.choice(PROSE_BEFORE) + compact({"name": n, "arguments": a})),
    ("prose_around", lambda r, n, a: r.choice(PROSE_BEFORE) + compact({"name": n, "arguments": a})
     + r.choice(PROSE_AFTER)),
    ("parameters_key", lambda r, n, a: compact({"parameters": a, "name": n})),
    ("raw_controls", lambda r, n, a: raw_controls(compact({"name": n, "arguments": a}))),
]


def assert_call(test, text, valid, name, args):
    calls, leftover = shim.extract_call(text, valid)
    test.assertIsNotNone(calls, text[:300])
    test.assertEqual(1, len(calls))
    call = calls[0]
    test.assertEqual("", leftover)
    test.assertRegex(call["id"], CALL_ID)
    test.assertEqual("function", call["type"])
    test.assertEqual(name, call["function"]["name"])
    got = call["function"]["arguments"]
    test.assertIsInstance(got, str)
    if isinstance(args, str):
        test.assertEqual(args, got)                    # a JSON string is passed on verbatim
    else:
        test.assertEqual(canonical(args), canonical(json.loads(got)))


def assert_prose(test, text, valid):
    test.assertEqual((None, text), shim.extract_call(text, valid))


# =============================================================================
# extract_call: generated calls, every wrapper, exact name and arguments back
# =============================================================================

class ExtractRoundTripTests(unittest.TestCase):
    """A generated call, wrapped as Llama wraps it, comes back exactly."""


def _round_trip_case(text, valid, name, args):
    def test(self):
        assert_call(self, text, valid, name, args)
    return test


ROUND_TRIP_CALLS = 18
for _seed in range(ROUND_TRIP_CALLS):
    _names, _name, _args = gen_call(1000 + _seed)
    _seen_texts = set()
    for _wname, _wrap in WRAPPERS:
        _text = _wrap(random.Random(_seed * 31 + len(_wname)), _name, _args)
        if _text in _seen_texts:
            continue                       # this wrapper changed nothing for this call
        _seen_texts.add(_text)
        add_test(ExtractRoundTripTests, "call%02d_%s" % (_seed, _wname),
                 _round_trip_case(_text, set(_names), _name, _args))


class ExtractRoundTripSanityTests(unittest.TestCase):
    """The generator itself produces what the round trips claim to cover."""

    def test_every_json_type_is_generated(self):
        kinds = set()

        def walk(v):
            kinds.add(type(v).__name__)
            if isinstance(v, dict):
                for x in v.values():
                    walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
        for seed in range(ROUND_TRIP_CALLS):
            walk(gen_call(1000 + seed)[2])
        self.assertEqual({"dict", "list", "str", "int", "float", "bool", "NoneType"}, kinds)

    def test_some_arguments_are_json_strings(self):
        self.assertTrue(any(isinstance(gen_call(1000 + s)[2], str) for s in range(ROUND_TRIP_CALLS)))

    def test_raw_controls_really_writes_raw_newlines_inside_strings(self):
        text = raw_controls(compact({"name": "w", "arguments": {"c": "a\nb\\n\t"}}))
        self.assertEqual('{"name":"w","arguments":{"c":"a\nb\\\\n\t"}}', text)
        self.assertRaises(ValueError, json.loads, text)          # strict JSON refuses it


# =============================================================================
# flatten_messages -> extract_call: pi's earlier calls come back as calls
# =============================================================================

FLATTEN_CONTENT = [None, "", "   ", "Reading it.", "I'll run two things.\nFirst this:"]


def gen_assistant_turn(seed):
    rng = random.Random(seed)
    names = gen_tool_names(rng, rng.randint(1, 6))
    calls = []
    for i in range(rng.randint(1, 3)):
        name = rng.choice(names)
        args = gen_object(rng, rng.randint(0, 3), name_key_ok=False)
        style = rng.choice(["dict", "string", "spaced_string", "invalid_string"])
        if style == "dict":
            sent, expect = args, args
        elif style == "string":
            sent, expect = compact(args), args
        elif style == "spaced_string":
            sent, expect = json.dumps(args, indent=1), args
        else:
            # Not JSON at all: flatten keeps it as a string and the parser
            # must hand that string back untouched.
            sent = rng.choice(["{oops", "path=a.py", "", "[1, 2", "{'a': 1}"]) + gen_string(rng, False)
            expect = sent
            try:
                expect = json.loads(sent)
            except ValueError:
                pass
        calls.append(({"id": "c%d" % i, "type": "function",
                       "function": {"name": name, "arguments": sent}}, name, expect))
    content = rng.choice(FLATTEN_CONTENT)
    return names, content, calls


def _expect_args(test, got, expect):
    if isinstance(expect, str):
        test.assertEqual(expect, got)
    else:
        test.assertEqual(canonical(expect), canonical(json.loads(got)))


class FlattenRoundTripTests(unittest.TestCase):
    """flatten_messages writes calls in the very form extract_call reads."""


def _flatten_first_case(names, content, calls):
    def test(self):
        msg = {"role": "assistant", "content": content, "tool_calls": [c for c, _, _ in calls]}
        out = shim.flatten_messages([msg])
        self.assertEqual(1, len(out))
        self.assertEqual("assistant", out[0]["role"])
        self.assertEqual({"role", "content"}, set(out[0]))
        got, leftover = shim.extract_call(out[0]["content"], set(names))
        self.assertIsNotNone(got, out[0]["content"][:300])
        self.assertEqual("", leftover)
        _, name, expect = calls[0]                 # one call per turn: the first wins
        self.assertEqual(name, got[0]["function"]["name"])
        _expect_args(self, got[0]["function"]["arguments"], expect)
    return test


def _flatten_lines_case(names, content, calls):
    def test(self):
        msg = {"role": "assistant", "content": content, "tool_calls": [c for c, _, _ in calls]}
        text = shim.flatten_messages([msg])[0]["content"]
        lines = text.split("\n")
        prose = (content or "").strip()
        prose_lines = len(prose.split("\n")) if prose else 0
        self.assertEqual(prose.split("\n") if prose else [], lines[:prose_lines])
        # One line per call, however many newlines the arguments held.
        self.assertEqual(len(calls), len(lines) - prose_lines)
        for line, (_, name, expect) in zip(lines[prose_lines:], calls):
            got, _ = shim.extract_call(line, set(names))
            self.assertIsNotNone(got, line[:300])
            self.assertEqual(name, got[0]["function"]["name"])
            _expect_args(self, got[0]["function"]["arguments"], expect)
    return test


for _seed in range(22):
    _turn = gen_assistant_turn(2000 + _seed)
    add_test(FlattenRoundTripTests, "turn%02d_first_call_parsed_back" % _seed, _flatten_first_case(*_turn))
    add_test(FlattenRoundTripTests, "turn%02d_each_line_parsed_back" % _seed, _flatten_lines_case(*_turn))


# =============================================================================
# tools_to_prompt: every tool listed once, schema intact
# =============================================================================

def schema_lines(prompt):
    head = "one JSON schema per line:\n\n"
    body = prompt[prompt.index(head) + len(head):prompt.index("\n\nTo call a function")]
    return body.split("\n") if body else []


DESCRIPTIONS = ["", "Read a file", "use {path} and {{x}}", "{tools}", "{0} {name!r}", "multi\nline\ndesc",
                "café 読み 🎉", 'quote " and \\ backslash', "ends with brace }", "%(x)s"]


def gen_schema(rng, depth):
    if depth <= 0 or rng.random() < 0.3:
        return {"type": rng.choice(["string", "integer", "boolean", "number"]),
                "description": rng.choice(DESCRIPTIONS)}
    props = {}
    for _ in range(rng.randint(0, 3)):
        props[gen_key(rng, True)] = gen_schema(rng, depth - 1)
    schema = {"type": "object", "properties": props}
    if props and rng.random() < 0.5:
        schema["required"] = sorted(props)[:1]
    if rng.random() < 0.2:
        schema["items"] = {"type": "array", "items": gen_schema(rng, depth - 1)}
    return schema


def gen_tools(seed):
    rng = random.Random(seed)
    names = gen_tool_names(rng, rng.randint(1, 10))
    tools, expected = [], []
    for name in names:
        fn = {"name": name}
        if rng.random() < 0.8:
            fn["description"] = rng.choice(DESCRIPTIONS)
        if rng.random() < 0.8:
            fn["parameters"] = gen_schema(rng, 3)
        if rng.random() < 0.2:
            fn["strict"] = True                    # extra keys are dropped
        expected.append({"name": name, "description": fn.get("description", ""),
                         "parameters": fn.get("parameters", {})})
        tools.append({"type": "function", "function": fn} if rng.random() < 0.7 else fn)
    return tools, expected


class ToolsPromptPropertyTests(unittest.TestCase):
    """The tool block lists each generated tool once, in order, schema intact."""


def _prompt_lines_case(tools, expected):
    def test(self):
        lines = schema_lines(shim.tools_to_prompt(tools))
        self.assertEqual(len(expected), len(lines))
        parsed = [json.loads(line) for line in lines]
        self.assertEqual([canonical(e) for e in expected], [canonical(p) for p in parsed])
        names = [p["name"] for p in parsed]
        for e in expected:
            self.assertEqual(1, names.count(e["name"]))
    return test


def _prompt_frame_case(tools, expected):
    def test(self):
        # Only the tool block differs from the empty prompt: no description is
        # ever read as a format field, and nothing leaks into the rules.
        prompt = shim.tools_to_prompt(tools)
        block = "\n".join(schema_lines(prompt))
        empty = shim.tools_to_prompt([])
        self.assertEqual(empty.replace("per line:\n\n\n\nTo call", "per line:\n\n" + block + "\n\nTo call"), prompt)
        self.assertEqual(1, prompt.count("\n\nTo call a function"))
    return test


def _prompt_names_callable_case(tools, expected):
    def test(self):
        # The names the prompt offers are exactly the names the parser accepts.
        lines = schema_lines(shim.tools_to_prompt(tools))
        valid = {json.loads(line)["name"] for line in lines}
        self.assertEqual({e["name"] for e in expected}, valid)
        for name in sorted(valid):
            assert_call(self, compact({"name": name, "arguments": {"k": name}}), valid, name, {"k": name})
    return test


for _seed in range(12):
    _tools, _expected = gen_tools(3000 + _seed)
    add_test(ToolsPromptPropertyTests, "tools%02d_each_listed_once_with_schema" % _seed,
             _prompt_lines_case(_tools, _expected))
    add_test(ToolsPromptPropertyTests, "tools%02d_frame_unchanged" % _seed,
             _prompt_frame_case(_tools, _expected))
    add_test(ToolsPromptPropertyTests, "tools%02d_listed_names_are_callable" % _seed,
             _prompt_names_callable_case(_tools, _expected))


# =============================================================================
# near misses: a reply without a valid tool name never becomes a call
# =============================================================================

def _mutations(name, names):
    """Spellings of a name that are not on the list, and names that are not strings."""
    out = [
        ("upper", name.upper()), ("title", name.title()), ("suffix", name + "_"),
        ("prefix", "_" + name), ("lead_space", " " + name), ("trail_space", name + " "),
        ("truncated", name[:-1]), ("doubled", name + name), ("dash_for_underscore", name.replace("_", "-")),
        ("newline", name + "\n"), ("zero_width", name + "\u200b"), ("fullwidth_first", chr(0xFF41) + name[1:]),
    ]
    return [(k, v) for k, v in out if isinstance(v, str) and v not in names]


NON_STRING_NAMES = [("null", None), ("number", 5), ("true", True), ("list", ["read"]), ("object", {"n": "read"})]


def gen_near_misses(seed):
    rng = random.Random(seed)
    names, name, args = gen_call(seed, name_key_ok=False)
    if isinstance(args, str):
        args = {"text": args}
    valid = set(names)
    cases = []
    for kind, wrong in _mutations(name, valid):
        cases.append((kind, compact({"name": wrong, "arguments": args})))
    kind, wrong = rng.choice(NON_STRING_NAMES)
    cases.append(("name_" + kind, compact({"name": wrong, "arguments": args})))
    good = compact({"name": name, "arguments": args})
    cases.append(("single_quoted", good.replace('"name"', "'name'", 1)))
    cases.append(("unquoted_name_key", good.replace('"name"', "name", 1)))
    cases.append(("trailing_comma", good[:-1] + ",}"))
    cases.append(("as_escaped_string", json.dumps({"text": good})))
    cases.append(("python_call", "%s(%s)" % (name, ", ".join("%s=%r" % (k, v) for k, v in
                                                            list(args.items())[:2]))))
    cases.append(("name_key_renamed", good.replace('"name"', '"tool"', 1)))
    rng.shuffle(cases)
    return valid, cases[:3]


class NearMissTests(unittest.TestCase):
    """Generated texts one step away from a call stay prose, unchanged."""


def _near_miss_case(text, valid):
    def test(self):
        assert_prose(self, text, valid)
    return test


for _seed in range(14):
    _valid, _cases = gen_near_misses(4000 + _seed)
    for _kind, _text in _cases:
        add_test(NearMissTests, "miss%02d_%s" % (_seed, _kind), _near_miss_case(_text, _valid))


class PrefixTests(unittest.TestCase):
    """No proper prefix of a generated call is a call: a reply cut off by
    max_tokens is shown as text, never run half-written."""


def _prefix_case(text, valid):
    def test(self):
        cuts = range(1, len(text))
        if len(text) > 3000:
            # Long strings: a spread of cuts, and every cut near the end.
            cuts = sorted(set(range(1, len(text), len(text) // 50)) | set(range(len(text) - 30, len(text))))
        for k in cuts:
            prefix = text[:k]
            calls, leftover = shim.extract_call(prefix, valid)
            if calls is not None:
                self.fail("prefix of length %d became a call: %r" % (k, prefix[-80:]))
            self.assertEqual(prefix, leftover)
        assert_call(self, text, valid, *json.loads(text, strict=False).values())
    return test


for _seed in range(16):
    _names, _name, _args = gen_call(5000 + _seed, name_key_ok=False)
    if isinstance(_args, str):
        _args = {"text": _args}
    add_test(PrefixTests, "call%02d_every_prefix_is_prose" % _seed,
             _prefix_case(compact({"name": _name, "arguments": _args}), set(_names)))


class NestedCallTests(unittest.TestCase):
    """An object inside a call's arguments is data, not a second call."""


# Was a bug: extract_call scanned every balanced {...} span containing "name",
# so when the outer object was not a valid call, an object nested inside its
# arguments that happened to carry a valid tool name was run as a call of its own.
NESTED = [
    ("unknown_tool_with_nested_call_in_arguments",
     '{"name":"create_task","arguments":{"step":{"name":"bash","arguments":{"command":"rm -rf build"}}}}'),
    ("malformed_call_with_nested_object_in_list",
     '{"name":"edit","arguments":{"edits":[{"name":"read","path":"a"}],}}'),
    ("non_string_name_with_nested_call",
     '{"name":null,"arguments":{"then":{"name":"write","arguments":{"path":"x"}}}}'),
    # Cut short by max_tokens: the outer object never closes, and what it holds
    # is still its arguments.
    ("truncated_call_with_nested_call_in_arguments",
     '{"name":"create_task","arguments":{"step":{"name":"bash","arguments":{"command":"rm -rf build"}}}'),
    ("truncated_pretty_call_with_nested_call",
     '{\n  "name": "edit",\n  "arguments": {"x": {"name": "read", "arguments": {}}}'),
]
for _name, _text in NESTED:
    add_test(NestedCallTests, _name, _near_miss_case(_text, {"bash", "read", "write", "edit_file"}))


class NestedCallSanityTests(unittest.TestCase):
    """Objects beside one another are still each looked at: only nesting hides one."""

    def test_valid_call_after_an_invalid_sibling(self):
        assert_call(self, '{"name":"create_task","arguments":{}} {"name":"bash","arguments":{"command":"ls"}}',
                    {"bash"}, "bash", {"command": "ls"})

    def test_valid_call_after_a_stray_brace_in_prose(self):
        assert_call(self, 'In C, if (x) { opens a block. ' + compact({"name": "read", "arguments": {"path": "a"}}),
                    {"read"}, "read", {"path": "a"})

    def test_openai_function_wrapper_is_still_the_call(self):
        assert_call(self, '{"type":"function","function":{"name":"read","arguments":{"path":"a"}}}',
                    {"read"}, "read", {"path": "a"})


class ParserCostTests(unittest.TestCase):
    """extract_call reads a reply in time proportional to its length: a write
    of a large file must not stall the shim. Measured by counting the
    characters _span_end walks, not by a clock, so the result is deterministic."""

    def scanned(self, text):
        walked = [0]
        real = shim._span_end

        def counting(s, start):
            end = real(s, start)
            walked[0] += (end if end is not None else len(s)) - start
            return end
        with mock.patch.object(shim, "_span_end", counting):
            calls, _ = shim.extract_call(text, {"write"})
        self.assertIsNotNone(calls)
        return walked[0], len(text)

    def test_balanced_code_is_scanned_a_bounded_number_of_times(self):
        code = "".join("function f%d(x) { if (x) { return {a: %d}; } }\n" % (i, i) for i in range(60))
        walked, size = self.scanned(compact({"name": "write", "arguments": {"path": "a.js", "content": code}}))
        self.assertLessEqual(walked, 4 * size)

    # Was a bug: every "{" started a fresh _span_end scan to the end of the
    # text, and a "{" inside a string never closes, so a write whose content
    # held n unclosed braces cost O(n^2): 12,000 braces took 45 s on an idle Mac.
    def test_unclosed_braces_in_a_string_are_scanned_a_bounded_number_of_times(self):
        walked, size = self.scanned(compact({"name": "write", "arguments": {"path": "a.txt", "content": "{" * 1500}}))
        self.assertLessEqual(walked, 4 * size)

    # Was a bug: _JSON_CALL (r'\{.*?"name"\s*:\s*".+?".*?\}\s*$') backtracked
    # over every quote when the reply did not end in "}", so a write of a JSON
    # file followed by one sentence of prose was quadratic: 400 records (25 KB,
    # 4,800 quotes) took 8.6 s. A clock is the only measure for a regex; the
    # 150 records here took about 1 s that way and take milliseconds now.
    def test_quote_heavy_content_with_prose_after_is_fast(self):
        data = json.dumps([{"id": i, "name": "item%d" % i, "tags": ["a", "b"]} for i in range(150)])
        text = compact({"name": "write", "arguments": {"path": "data.json", "content": data}}) + "\nI have written it."
        started = time.perf_counter()
        calls, _ = shim.extract_call(text, {"write"})
        elapsed = time.perf_counter() - started
        self.assertEqual(data, json.loads(calls[0]["function"]["arguments"])["content"])
        self.assertLess(elapsed, 0.2)

    def test_unclosed_braces_in_prose_are_scanned_a_bounded_number_of_times(self):
        # Stray braces outside any string, before the call: none can open a
        # JSON object, so none starts a scan, and the call is still found.
        walked, size = self.scanned("{ " * 6000 + compact({"name": "write", "arguments": {"path": "a"}}))
        self.assertLessEqual(walked, 4 * size)

    def test_long_whitespace_before_a_closing_fence_is_fast(self):
        # The fence used to be stripped by r"\s*```$", which retries every
        # whitespace run to its end: 20,000 spaces took 1.5 s.
        text = compact({"name": "write", "arguments": {"path": "a", "content": "a" + " " * 20000 + "b"}})
        started = time.perf_counter()
        calls, _ = shim.extract_call("```json\n" + text + "\n```", {"write"})
        self.assertLess(time.perf_counter() - started, 0.2)
        self.assertEqual("a" + " " * 20000 + "b", json.loads(calls[0]["function"]["arguments"])["content"])


# =============================================================================
# egress: a reference model of the allowlist, and generated hosts
# =============================================================================

def _is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def reference_allowed(allow, host):
    """LOCKDOWN.md's rule, spelled differently from Proxy.allowed: compare
    dot-separated labels from the right. Entries lose dots at both ends (a
    leading dot is the "and subdomains" spelling, a trailing one the absolute
    FQDN); hosts lose trailing dots; letters compare without case; an IP
    literal passes only in a spelling that is listed; a "*" entry opens all."""
    entries = []
    for entry in allow:
        if not entry:
            continue
        e = entry.lower()
        while e[:1] == ".":
            e = e[1:]
        while e[-1:] == ".":
            e = e[:-1]
        entries.append(e)
    if "*" in entries:
        return True
    h = host.lower()
    while h[-1:] == ".":
        h = h[:-1]
    if _is_ip(h):
        return h in entries
    labels = h.split(".")
    for e in entries:
        want = e.split(".")
        if len(labels) >= len(want) and labels[len(labels) - len(want):] == want:
            return True
    return False


ALPHA = "ab0-"
TLDS = ["org", "io", "uk", "dev", "com"]


def gen_label(rng, lo=1, hi=4):
    return "".join(rng.choice(ALPHA) for _ in range(rng.randint(lo, hi)))


def gen_domain(rng):
    while True:
        labels = [gen_label(rng) for _ in range(rng.randint(1, 2))] + [rng.choice(TLDS)]
        name = ".".join(labels)
        if not _is_ip(name):
            return name


def spell(rng, name):
    """The same entry as someone might write it: case, leading or trailing dot."""
    s = "".join(c.upper() if rng.random() < 0.3 else c for c in name)
    r = rng.random()
    if r < 0.2:
        s = "." + s
    elif r < 0.35:
        s = s + "."
    return s


def gen_allowlist(seed):
    rng = random.Random(seed)
    names = []
    while len(names) < rng.randint(1, 4):
        d = gen_domain(rng)
        if d not in names:
            names.append(d)
    # Sometimes an entry is itself under another: the wider one decides.
    if rng.random() < 0.5:
        names.append(gen_label(rng) + "." + names[0])
    ipv4 = ["10.%d.%d.%d" % (rng.randint(0, 255), rng.randint(0, 255), rng.randint(1, 254))] \
        if rng.random() < 0.7 else []
    ipv6 = ["2001:db8::%x" % rng.randint(1, 0xffff)] if rng.random() < 0.6 else []
    allow = [spell(rng, n) for n in names] + ipv4 + ipv6
    rng.shuffle(allow)
    return allow, names, ipv4, ipv6


def norm_entries(allow):
    return [e.lower().strip(".") for e in allow if e]


ALLOWLISTS = [("shipped", SHIPPED, [n.lower() for n in SHIPPED], [], [])]
for _i in range(8):
    _allow, _names, _v4, _v6 = gen_allowlist(6000 + _i)
    ALLOWLISTS.append(("gen%d" % _i, _allow, _names, _v4, _v6))
# One list certainly has both IP kinds, in a spelling to normalise.
_n, _allow, _names, _v4, _v6 = ALLOWLISTS[1]
ALLOWLISTS[1] = (_n, _allow + ["10.1.2.3", "2001:DB8::1"], _names, _v4 + ["10.1.2.3"], _v6 + ["2001:db8::1"])


def ipv4_spellings(ip):
    """Other ways to write the same IPv4 address; none of them is the listed text."""
    a, b, c, d = (int(x) for x in ip.split("."))
    n = (a << 24) | (b << 16) | (c << 8) | d
    return [str(n), hex(n), "%d.%d" % (a, (b << 16) | (c << 8) | d), "%d.%d.%d" % (a, b, (c << 8) | d),
            ".".join("0x%x" % x for x in (a, b, c, d)), ".".join("%03d" % x for x in (a, b, c, d)),
            ".".join("0%o" % x if x else "0" for x in (a, b, c, d)), "::ffff:" + ip, "::ffff:%x:%x" % (n >> 16, n & 0xffff),
            "[%s]" % ip, ip + "%en0"]


def ipv6_spellings(ip):
    addr = ipaddress.ip_address(ip)
    return [addr.exploded, addr.exploded.upper().replace("2001", "2001:0"),
            "[%s]" % ip, ip + "%en0", ip.replace("::", ":0::", 1), "::ffff:" + ip.split(":")[-1],
            str(ipaddress.ip_address(int(addr) + 1)), str(addr).replace("::", ":0:0:0:0:0:", 1)]


def host_families(allowlist, seed):
    """Families of generated hosts for one allowlist: name -> [hosts]."""
    _, allow, names, ipv4, ipv6 = allowlist
    rng = random.Random(seed)
    entries = [n for n in norm_entries(allow) if not _is_ip(n)]
    fam = {}
    fam["exact"] = [spell(rng, e).lstrip(".") + "." * rng.randint(0, 2) for e in entries for _ in range(4)]
    fam["subdomain"] = [".".join(gen_label(rng) for _ in range(rng.randint(1, 3))) + "." + spell(rng, e).lstrip(".")
                        for e in entries for _ in range(8)]
    fam["parent"] = [".".join(e.split(".")[k:]) for e in entries for k in range(1, len(e.split(".")))] + \
                    ["." + e.split(".")[-1] for e in entries] + [e.split(".")[-1] + "." for e in entries]
    fam["glued_prefix"] = [gen_label(rng) + e for e in entries for _ in range(5)] + \
                          [e[1:] for e in entries if len(e) > 1] + \
                          [(ALPHA[(ALPHA.index(e[0]) + 1) % len(ALPHA)] if e[0] in ALPHA else "z") + e[1:]
                           for e in entries]
    fam["appended"] = [e + "." + gen_label(rng) for e in entries for _ in range(3)] + \
                      [e + gen_label(rng) for e in entries for _ in range(3)] + \
                      [e + "-" + gen_label(rng) + "." + rng.choice(TLDS) for e in entries] + \
                      [e + "." + e for e in entries]
    fam["random"] = [".".join([gen_label(rng) for _ in range(rng.randint(0, 3))] + [rng.choice(TLDS)])
                     for _ in range(150)]
    fam["punycode"] = ["xn--" + gen_label(rng) + "-" + gen_label(rng) + "." + e for e in entries] + \
                      ["xn--" + e.replace(".", "-") for e in entries] + \
                      [e.replace(e.split(".")[0], "xn--" + e.split(".")[0] + "-9ja", 1) for e in entries] + \
                      [e.replace("a", "\u0430", 1) for e in entries if "a" in e] + \
                      [e.replace("0", "\u0660", 1) for e in entries if "0" in e] + \
                      [("\u0430" + e[1:]).encode("idna").decode("ascii") for e in entries
                       if e[0] == "a" and all(x for x in e.split("."))] + \
                      [e.replace(".", "\u3002") for e in entries] + [e + "\u200b" for e in entries]
    fam["dots"] = [e + "." * rng.randint(1, 3) for e in entries] + ["." + e for e in entries] + \
                  [gen_label(rng) + ".." + e for e in entries] + [e.replace(".", "..", 1) for e in entries] + \
                  ["." * rng.randint(1, 3) for _ in range(2)]
    fam["junk"] = [e + ":443" for e in entries] + [e + "/" for e in entries] + [" " + e for e in entries] + \
                  [e + "\n" for e in entries] + ["user@" + e for e in entries] + [e + "@evil.org" for e in entries] + \
                  ["*." + e for e in entries] + ["*", "", " "]
    if ipv4:
        fam["ipv4"] = [s for ip in ipv4 for s in [ip] + ipv4_spellings(ip)] + \
                      ["%s.%d" % (ip.rsplit(".", 1)[0], (int(ip.rsplit(".", 1)[1]) + 1) % 256) for ip in ipv4] + \
                      ["127.0.0.1", "169.254.169.254", "0.0.0.0"]
    if ipv6:
        fam["ipv6"] = [s for ip in ipv6 for s in [ip, ip.upper()] + ipv6_spellings(ip)] + ["::1", "::", "fe80::1"]
    return fam


class AllowlistModelTests(unittest.TestCase):
    """Proxy.allowed agrees with the reference model, family by family."""


# What a family must be, whatever else is on the list: exact spellings and
# subdomains of an entry always pass. (Junk is not forced to fail: " a.x.org"
# is a subdomain of "x.org" when "a.x.org" and "x.org" are both listed.)
FAMILY_FORCED = {"exact": True, "subdomain": True}


def _model_case(allow, hosts, forced):
    def test(self):
        proxy = egress.Proxy(allow, os.devnull)
        self.assertGreater(len(hosts), 0)
        for host in hosts:
            want = reference_allowed(allow, host)
            if forced is not None:
                self.assertEqual(forced, want, "reference model disagrees with the family: %r" % host)
            self.assertEqual(want, proxy.allowed(host), "allow=%r host=%r" % (allow, host))
    return test


ALL_HOSTS = {}
for _k, _al in enumerate(ALLOWLISTS):
    _fams = host_families(_al, 7000 + _k)
    ALL_HOSTS[_al[0]] = [h for hs in _fams.values() for h in hs]
    for _fname, _hosts in _fams.items():
        add_test(AllowlistModelTests, "%s_%s" % (_al[0], _fname),
                 _model_case(_al[1], _hosts, FAMILY_FORCED.get(_fname)))


class AllowlistModelSanityTests(unittest.TestCase):
    """The model and the generators are not trivially one-sided."""

    def test_every_list_has_hosts_on_both_sides(self):
        for name, allow, *_ in ALLOWLISTS:
            verdicts = {reference_allowed(allow, h) for h in ALL_HOSTS[name]}
            self.assertEqual({True, False}, verdicts, name)

    def test_thousands_of_hosts_are_checked(self):
        self.assertGreater(sum(len(v) for v in ALL_HOSTS.values()), 3000)

    def test_listed_ip_spellings_are_all_one_address(self):
        # The alternative spellings really are the listed address, so their
        # refusal is the "only as listed" rule and not a typo in the generator.
        for ip in ("10.1.2.3",):
            for s in ipv4_spellings(ip)[:2]:
                self.assertEqual(ipaddress.ip_address(ip), ipaddress.ip_address(int(s, 0)))
        self.assertEqual(ipaddress.ip_address("2001:db8::1"),
                         ipaddress.ip_address(ipv6_spellings("2001:db8::1")[0]))


class AllowlistAlgebraTests(unittest.TestCase):
    """Order does not matter, adding an entry never takes access away, and a
    union of lists allows exactly what either part allows."""


def _order_case(allow, hosts, seed):
    def test(self):
        shuffled = list(allow)
        random.Random(seed).shuffle(shuffled)
        a, b = egress.Proxy(allow, os.devnull), egress.Proxy(list(reversed(shuffled)), os.devnull)
        self.assertEqual([a.allowed(h) for h in hosts], [b.allowed(h) for h in hosts])
    return test


def _monotonic_case(allow, hosts, seed):
    def test(self):
        extra = gen_domain(random.Random(seed))
        before = egress.Proxy(allow, os.devnull)
        after = egress.Proxy(allow + [extra], os.devnull)
        gained = 0
        for h in hosts + [extra, "a." + extra]:
            if before.allowed(h):
                self.assertTrue(after.allowed(h), h)
            elif after.allowed(h):
                gained += 1
                self.assertTrue(reference_allowed([extra], h), h)   # only what the new entry covers
        self.assertGreater(gained, 0)
    return test


def _union_case(allow, other, hosts):
    def test(self):
        a, b = egress.Proxy(allow, os.devnull), egress.Proxy(other, os.devnull)
        both = egress.Proxy(allow + other, os.devnull)
        for h in hosts:
            self.assertEqual(a.allowed(h) or b.allowed(h), both.allowed(h), h)
    return test


for _k, _al in enumerate(ALLOWLISTS):
    _other = ALLOWLISTS[(_k + 1) % len(ALLOWLISTS)]
    _hosts = ALL_HOSTS[_al[0]] + ALL_HOSTS[_other[0]][:200]
    add_test(AllowlistAlgebraTests, "%s_order_does_not_matter" % _al[0], _order_case(_al[1], _hosts, _k))
    add_test(AllowlistAlgebraTests, "%s_adding_an_entry_only_adds" % _al[0], _monotonic_case(_al[1], _hosts, 8000 + _k))
    add_test(AllowlistAlgebraTests, "%s_union_with_%s" % (_al[0], _other[0]), _union_case(_al[1], _other[1], _hosts))


class OpenModeModelTests(unittest.TestCase):
    """With "*" on the list every host passes, and note_open records each
    distinct host once, lowercased without its trailing dots, in first-seen order."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="elm-pi-props-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def _open_case(name, allow, hosts, seed):
    def test(self):
        log = os.path.join(self.tmp, "egress.log")
        proxy = egress.Proxy(allow + ["*"] if seed % 2 else ["*"] + allow, log)
        rng = random.Random(seed)
        # Each host visited several times, in several spellings.
        visits = [rng.choice([h, h.upper(), h + ".", h.title() + ".."]) for h in hosts for _ in range(3)]
        rng.shuffle(visits)
        order = []
        for v in visits:
            self.assertTrue(proxy.allowed(v), repr(v))
            proxy.note_open(v)
            key = v.lower().rstrip(".")
            if key not in order:
                order.append(key)
        text = Path(log).read_text(encoding="utf-8") if os.path.exists(log) else ""
        got = [line[21:] for line in text.splitlines()]
        self.assertEqual(["OPEN     %s no allowlist in this install (--allow '*')" % h for h in order], got)
    return test


for _k, _al in enumerate(ALLOWLISTS):
    _hosts = [h for h in ALL_HOSTS[_al[0]] if h.strip() and "\n" not in h][:60]
    add_test(OpenModeModelTests, "%s_star_opens_and_records_once" % _al[0],
             _open_case(_al[0], _al[1], _hosts, 9000 + _k))


# =============================================================================
# egress: generated request lines through Proxy.handle()
# =============================================================================

class FakeClient:
    """The client end of a connection: hands over the request, keeps the reply."""

    def __init__(self, data):
        self.chunks = [data]
        self.sent = b""
        self.closed = False

    def settimeout(self, t):
        pass

    def recv(self, n):
        return self.chunks.pop(0) if self.chunks else b""

    def sendall(self, data):
        self.sent += data

    def close(self):
        self.closed = True


class FakeServer(FakeClient):
    def __init__(self):
        super().__init__(b"")


class RequestLineCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="elm-pi-props-")
        self.n = 0

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_line(self, allow, request):
        """Drive handle() on one request. Returns (proxy, client, tunnels, dials, splices)."""
        self.n += 1
        proxy = egress.Proxy(allow, os.path.join(self.tmp, "egress-%d.log" % self.n))
        tunnels, dials, splices = [], [], []
        proxy.connect_through = lambda client, host, port, head, pending=b"": tunnels.append((host, port))
        proxy.splice = lambda a, b, target="?": splices.append((b, target))

        def dial(address, timeout=None):
            dials.append(address)
            return FakeServer()
        client = FakeClient(request)
        with mock.patch.object(egress.socket, "create_connection", dial):
            proxy.handle(client, ("127.0.0.1", 0))
        self.assertTrue(client.closed)
        return proxy, client, tunnels, dials, splices

    def log_lines(self, proxy):
        try:
            text = Path(proxy.log_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        return [line[21:] for line in text.splitlines()]

    def assert_refused(self, proxy, client, tunnels, dials, host, port):
        self.assertTrue(client.sent.startswith(b"HTTP/1.1 403 Forbidden\r\n"), client.sent[:80])
        self.assertEqual(1, client.sent.count(b"HTTP/1.1 "))
        self.assertEqual(["REJECTED %s:%s not on the allowlist" % (host, port)], self.log_lines(proxy))
        self.assertEqual([], tunnels)
        self.assertEqual([], dials)


def bracket(host):
    return "[%s]" % host if ":" in host else host


def gen_target_hosts(allowlist, seed, want_allowed, count):
    """Hosts for request lines, from the allowlist's families, that the
    reference allows (or refuses) and that can appear in a request line."""
    rng = random.Random(seed)
    fams = host_families(allowlist, seed)
    pool = [h for hs in fams.values() for h in hs]
    pool = [h for h in pool
            if h and not any(c in h for c in " \t\r\n/?#@[]%\u3002\u200b") and not h.endswith(":443")
            and all(ord(c) < 256 for c in h) and (":" not in h or _is_ip(h))
            and reference_allowed(allowlist[1], h) == want_allowed]
    rng.shuffle(pool)
    return pool[:count]


PORTS = ["443", "80", "8443", "1", "65535", "08080"]


def urllib_authority(text):
    parts = urllib.parse.urlsplit("//" + text)
    return parts.hostname, parts.port


class ConnectLineTests(RequestLineCase):
    """Generated CONNECT lines: urllib's host and port, the reference verdict,
    the same verdict on every port, and one log line per refusal."""


def _connect_case(allow, hosts, want_allowed, seed):
    def test(self):
        rng = random.Random(seed)
        self.assertGreater(len(hosts), 0)
        for host in hosts:
            for port in rng.sample(PORTS, 3):
                target = bracket(host) + ":" + port
                ref_host, ref_port = urllib_authority(target)
                self.assertEqual((host.lower(), int(port)), (ref_host, ref_port))   # the generator's truth
                method = rng.choice(["CONNECT", "connect", "Connect"])
                version = rng.choice([" HTTP/1.1", " HTTP/1.0", ""])
                extra = rng.choice(["", "Host: %s\r\n" % target, "Host: pypi.org:443\r\nUser-Agent: x\r\n"])
                request = ("%s %s%s\r\n%s\r\n" % (method, target, version, extra)).encode("latin-1")
                proxy, client, tunnels, dials, _ = self.run_line(allow, request)
                if want_allowed:
                    self.assertEqual(1, len(tunnels), request)
                    got_host, got_port = tunnels[0]
                    self.assertEqual((ref_host, ref_port), (got_host.lower(), int(got_port)))
                    self.assertEqual(host, got_host)                 # dialled as written
                    self.assertEqual([], self.log_lines(proxy))     # allowed tunnels are not logged
                    self.assertEqual(b"", client.sent)
                else:
                    self.assert_refused(proxy, client, tunnels, dials, host, port)
    return test


def _connect_default_port_case(allow, hosts):
    def test(self):
        for host in hosts:
            proxy, client, tunnels, dials, _ = self.run_line(allow, ("CONNECT %s HTTP/1.1\r\n\r\n" % host).encode())
            if reference_allowed(allow, host):
                self.assertEqual([(host, "443")], tunnels)
            else:
                self.assert_refused(proxy, client, tunnels, dials, host, "443")
    return test


for _k, _al in enumerate(ALLOWLISTS):
    _ok = gen_target_hosts(_al, 10000 + _k, True, 14)
    _no = gen_target_hosts(_al, 11000 + _k, False, 14)
    add_test(ConnectLineTests, "%s_allowed_hosts_tunnel_to_urllib_host_and_port" % _al[0],
             _connect_case(_al[1], _ok, True, 12000 + _k))
    add_test(ConnectLineTests, "%s_refused_hosts_logged_once_on_every_port" % _al[0],
             _connect_case(_al[1], _no, False, 13000 + _k))
    add_test(ConnectLineTests, "%s_no_port_means_443" % _al[0],
             _connect_default_port_case(_al[1], [h for h in _ok + _no if ":" not in h][:16]))
    _ips = [h for h in gen_target_hosts(_al, 14000 + _k, True, 400) + gen_target_hosts(_al, 14500 + _k, False, 400)
            if _is_ip(h)]
    if _ips:
        add_test(ConnectLineTests, "%s_ip_literals_bracketed_and_ported" % _al[0],
                 _connect_case(_al[1], [h for h in _ips if reference_allowed(_al[1], h)], True, 15000 + _k)
                 if any(reference_allowed(_al[1], h) for h in _ips)
                 else _connect_case(_al[1], _ips, False, 15000 + _k))


class ConnectLineBugTests(RequestLineCase):
    """CONNECT forms the proxy reads differently from urllib."""

    # Was a bug: a bracketed IPv6 CONNECT target without a port was split at its
    # last colon ("[2001:db8:" / "1]"), so a listed address was refused as
    # "2001:db8::1]" instead of being tunnelled to port 443 like a name without
    # a port is.
    def test_bracketed_ipv6_without_port_is_listed_address_on_443(self):
        _, _, tunnels, _, _ = self.run_line(["2001:db8::1"], b"CONNECT [2001:db8::1] HTTP/1.1\r\n\r\n")
        self.assertEqual([("2001:db8::1", "443")], tunnels)

    def test_bracketed_unlisted_ipv6_without_port_is_refused_on_443(self):
        proxy, client, tunnels, dials, _ = self.run_line(["2001:db8::1"], b"CONNECT [2001:db8::2] HTTP/1.1\r\n\r\n")
        self.assert_refused(proxy, client, tunnels, dials, "2001:db8::2", "443")


METHODS = ["GET", "POST", "HEAD", "PUT", "DELETE", "get", "Options"]
PATHS = ["", "/", "/simple/", "/a/b.whl", "?q=1", "/p?q=1&r=2", "/%7Euser/x", "/a:b@c", "/x?next=http://evil.org/"]


def gen_plain(host, rng):
    port = rng.choice([None, "80", "8080", "1", "65535"])
    path = rng.choice(PATHS)
    scheme = rng.choice(["http", "HTTP", "Http"])
    authority = bracket(host) + ("" if port is None else ":" + port)
    return scheme + "://" + authority + path, port or "80", path


class PlainLineTests(RequestLineCase):
    """Generated absolute-URI lines: the host and port dialled and the
    origin-form line sent are urllib's reading of the URI."""


def _plain_case(allow, hosts, want_allowed, seed):
    def test(self):
        rng = random.Random(seed)
        self.assertGreater(len(hosts), 0)
        for host in hosts:
            for _ in range(2):
                uri, port, path = gen_plain(host, rng)
                parts = urllib.parse.urlsplit(uri)
                self.assertEqual((host.lower(), int(port)), (parts.hostname, parts.port or 80))
                method = rng.choice(METHODS)
                version = rng.choice(["HTTP/1.1", "HTTP/1.0"])
                tail = "Host: %s\r\nAccept: */*\r\n\r\n" % parts.netloc
                body = rng.choice([b"", b"payload"])
                request = ("%s %s %s\r\n%s" % (method, uri, version, tail)).encode("latin-1") + body
                proxy, client, tunnels, dials, splices = self.run_line(allow, request)
                if want_allowed:
                    self.assertEqual([(host, int(port))], dials, uri)
                    origin = (parts.path or "/") + ("?" + parts.query if parts.query else "")
                    want = ("%s %s %s\r\n%s" % (method.upper(), origin, version, tail)).encode("latin-1") + body
                    self.assertEqual(want, splices[0][0].sent)
                    self.assertEqual("%s:%s" % (host, port), splices[0][1])
                    self.assertEqual([], self.log_lines(proxy))
                else:
                    self.assert_refused(proxy, client, tunnels, dials, host, port)
    return test


for _k, _al in enumerate(ALLOWLISTS):
    _ok = gen_target_hosts(_al, 16000 + _k, True, 12)
    _no = gen_target_hosts(_al, 17000 + _k, False, 12)
    add_test(PlainLineTests, "%s_allowed_uris_forwarded_as_urllib_reads_them" % _al[0],
             _plain_case(_al[1], _ok, True, 18000 + _k))
    add_test(PlainLineTests, "%s_refused_uris_logged_once" % _al[0],
             _plain_case(_al[1], _no, False, 19000 + _k))


class PlainLineAuthorityTests(RequestLineCase):
    """Authorities urllib reads as an allowed host that the proxy must not
    read as anything wider: userinfo, and hosts hidden in query or fragment."""


def _hidden_host_case(allowed_host, uri_fmt, dial_host):
    def test(self):
        uri = uri_fmt.format(h=allowed_host)
        proxy, client, tunnels, dials, _ = self.run_line(SHIPPED, ("GET %s HTTP/1.1\r\n\r\n" % uri).encode())
        parts = urllib.parse.urlsplit(uri)
        self.assertEqual(dial_host, parts.hostname)
        # The proxy's host is the authority as written; when that is not
        # urllib's host, the proxy refuses rather than guessing.
        if reference_allowed(SHIPPED, parts.hostname) and "@" not in parts.netloc:
            self.assertEqual([(parts.hostname, parts.port or 80)], dials)
        else:
            self.assertEqual([], dials)
            self.assertEqual(1, len(self.log_lines(proxy)))
            self.assertTrue(self.log_lines(proxy)[0].startswith("REJECTED "))
    return test


for _k, _h in enumerate(sorted(set(SHIPPED))[:6]):
    add_test(PlainLineAuthorityTests, "query_host_is_not_the_host_%s" % slug(_h),
             _hidden_host_case(_h, "http://evil.org?.{h}/", "evil.org"))
    add_test(PlainLineAuthorityTests, "fragment_host_is_not_the_host_%s" % slug(_h),
             _hidden_host_case(_h, "http://evil.org#.{h}", "evil.org"))
    add_test(PlainLineAuthorityTests, "userinfo_is_refused_%s" % slug(_h),
             _hidden_host_case(_h, "http://u:p@{h}/simple/", _h))


class PlainLineBugTests(RequestLineCase):
    """Absolute URIs the proxy reads differently from urllib."""

    # Was a bug: an empty port ("http://pypi.org:/", which RFC 3986 allows and
    # urllib reads as the default port) was taken as part of the host, so the
    # listed host was refused as "pypi.org::80".
    def test_empty_port_is_the_default_port(self):
        _, _, _, dials, _ = self.run_line(SHIPPED, b"GET http://pypi.org:/simple/ HTTP/1.1\r\n\r\n")
        self.assertEqual([("pypi.org", 80)], dials)

    def test_empty_port_does_not_widen_the_allowlist(self):
        for uri, host in ((b"http://evil.org:/", "evil.org"), (b"http://[2001:db8::1]:/", "2001:db8::1"),
                          (b"http://pypi.org.evil.org:/", "pypi.org.evil.org")):
            proxy, client, tunnels, dials, _ = self.run_line(SHIPPED, b"GET " + uri + b" HTTP/1.1\r\n\r\n")
            self.assert_refused(proxy, client, tunnels, dials, host, "80")


class OpenModeLineTests(RequestLineCase):
    """In open mode every generated line is let through and each host is
    recorded once, however many times and spellings it arrives in."""


def _open_lines_case(hosts, seed):
    def test(self):
        rng = random.Random(seed)
        proxy = egress.Proxy(["*"], os.path.join(self.tmp, "open.log"))
        tunnels = []
        proxy.connect_through = lambda client, host, port, head, pending=b"": tunnels.append((host, port))
        order, sent = [], 0
        for _ in range(3):
            for host in hosts:
                spelt = rng.choice([host, host.upper(), host + "."])
                client = FakeClient(("CONNECT %s:%s HTTP/1.1\r\n\r\n" % (bracket(spelt), rng.choice(PORTS))).encode())
                proxy.handle(client, ("127.0.0.1", 0))
                sent += 1
                key = spelt.lower().rstrip(".")
                if key not in order:
                    order.append(key)
        self.assertEqual(sent, len(tunnels))
        self.assertEqual(["OPEN     %s no allowlist in this install (--allow '*')" % h for h in order],
                         self.log_lines(proxy))
    return test


for _k, _al in enumerate(ALLOWLISTS):
    _hosts = gen_target_hosts(_al, 20000 + _k, True, 6) + gen_target_hosts(_al, 20500 + _k, False, 6)
    add_test(OpenModeLineTests, "%s_hosts_recorded_once" % _al[0], _open_lines_case(_hosts, 21000 + _k))


if __name__ == "__main__":
    unittest.main()
