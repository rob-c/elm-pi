"""The Llama tool-call shim: text calls in, OpenAI tool_calls out, and back again.

shim/shim.py is imported directly for the parsing and rewriting functions, and
served in-process on 127.0.0.1 against a fake upstream (also on 127.0.0.1) for
the HTTP behaviour: what is sent to ELM, what comes back to pi, streaming,
passthrough and errors. One real `python3 -E -S shim.py` process proves the
standalone start-up and that it listens on loopback only, and one node process
runs templates/extensions/elm-shim.ts against a stub pi to read the provider it
registers. Nothing here talks to anything but 127.0.0.1.

Most cases are tables: each row becomes its own test method, so a failure names
the exact input that broke.
"""

import http.client
import http.server
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / "shim/shim.py"
EXTENSION = ROOT / "templates/extensions/elm-shim.ts"
LLAMA = "meta-llama/Llama-3.3-70B-Instruct"
EUROLLM = "utter-project/EuroLLM-22B-Instruct-2512"
QWEN = "Qwen/Qwen3-32B"
VALID = {"read", "write", "edit", "bash", "ls", "grep"}
CALL_ID = re.compile(r"^call_[0-9a-f]{16}$")
PROXY_VARS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")


def load_shim(name):
    spec = importlib.util.spec_from_file_location(name, SHIM)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def canonical(value):
    # Order- and type-preserving: 1, 1.0, True and "1" all serialise differently.
    return json.dumps(value, ensure_ascii=False)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def closed_port():
    # Bound and released: nothing listens there for the life of the test.
    return free_port()


def add_cases(cls, prefix, cases, run):
    """One test method per row; a row whose last field is a bug note is an expected failure."""
    for case in cases:
        slug, *args = case
        bug = None
        if args and isinstance(args[-1], Bug):
            bug = args.pop()
        name = f"test_{prefix}_{slug}"
        assert name not in cls.__dict__, f"duplicate case {name}"

        def method(self, _args=tuple(args)):
            run(self, *_args)
        method.__name__ = name
        if bug:
            method.__doc__ = f"KNOWN BUG: {bug}"
            method = unittest.expectedFailure(method)
        setattr(cls, name, method)


class Bug(str):
    """Marks a table row that shows a real bug in shim.py (run as expectedFailure)."""


# --- local HTTP fixtures ------------------------------------------------------

class FakeUpstream(http.server.ThreadingHTTPServer):
    """Stands in for ELM (or for the egress proxy): records requests, plays back replies."""
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), FakeUpstreamHandler)
        self.requests = []
        self.reply = (200, "application/json", b"{}")
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self):
        return self.server_address[1]

    def stop(self):
        self.shutdown()
        self.server_close()


class FakeUpstreamHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        self.server.requests.append({"method": self.command, "path": self.path,
                                     "headers": {k.lower(): v for k, v in self.headers.items()},
                                     "body": body})
        status, ctype, payload = self.server.reply
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = _handle


def completion(content, finish="stop", **extra):
    """An upstream (vLLM) chat completion carrying `content`."""
    body = {"id": "chatcmpl-up1", "object": "chat.completion", "created": 1700000000,
            "model": LLAMA,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                         "finish_reason": finish}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}}
    body.update(extra)
    return body


TOOLS = [
    {"type": "function", "function": {"name": "read", "description": "Read a file",
                                      "parameters": {"type": "object",
                                                     "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "bash", "description": "Run a command",
                                      "parameters": {"type": "object",
                                                     "properties": {"command": {"type": "string"}}}}},
]


class ShimServerCase(unittest.TestCase):
    """Base: a fresh shim module served on 127.0.0.1, in front of a fake upstream."""

    @classmethod
    def setUpClass(cls):
        cls.env = mock.patch.dict(os.environ)
        cls.env.start()
        for key in PROXY_VARS + ("SHIM_TEMPERATURE",):
            os.environ.pop(key, None)
        cls.shim = load_shim(f"elm_pi_shim_{cls.__name__}")
        cls.upstream = FakeUpstream()
        cls.shim.UPSTREAM = f"http://127.0.0.1:{cls.upstream.port}/api/v1"
        cls.shim.PROXY_MANAGED = False

        class Quiet(cls.shim.Server):
            # A crashing handler would print a traceback per case; the tests read the outcome.
            def handle_error(self, request, client_address):
                pass

        cls.server = Quiet(("127.0.0.1", 0), cls.shim.Handler)
        cls.port = cls.server.server_address[1]
        cls.shim.PORT = cls.port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.upstream.stop()
        cls.env.stop()

    def setUp(self):
        self.upstream.requests.clear()
        self.upstream.reply = (200, "application/json", b"{}")

    def reply_with(self, body, status=200, ctype="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.upstream.reply = (status, ctype, raw)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            raw = body if body is None or isinstance(body, bytes) else json.dumps(body).encode()
            conn.request(method, path, body=raw, headers={"Content-Type": "application/json",
                                                          **(headers or {})})
            resp = conn.getresponse()
            return resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read()
        finally:
            conn.close()

    def chat(self, payload, path="/v1/chat/completions", headers=None):
        payload = {"model": LLAMA, "messages": [{"role": "user", "content": "hi"}],
                   "tools": TOOLS, **payload}
        return self.request("POST", path, payload, headers)

    def sent(self):
        """The JSON body the shim sent upstream on the one request it made."""
        self.assertEqual(1, len(self.upstream.requests))
        return json.loads(self.upstream.requests[0]["body"])


def sse_events(raw):
    return [line[len("data: "):] for line in raw.decode().split("\n") if line.startswith("data: ")]


# =============================================================================
# extract_call: which texts become a tool call
# =============================================================================

READ_A = '{"name":"read","arguments":{"path":"a.py"}}'

# (slug, model text, valid names, expected name, expected arguments as an object)
RECOGNISED = [
    ("bare_compact", READ_A, VALID, "read", {"path": "a.py"}),
    ("bare_spaced", '{ "name" : "read" , "arguments" : { "path" : "a.py" } }', VALID, "read", {"path": "a.py"}),
    # Llama 3.3's own JSON tool format says "parameters", not "arguments".
    ("parameters_key", '{"name":"read","parameters":{"path":"a.py"}}', VALID, "read", {"path": "a.py"}),
    ("type_function_parameters", '{"type":"function","name":"read","parameters":{"path":"a.py"}}',
     VALID, "read", {"path": "a.py"}),
    ("arguments_win_over_parameters", '{"name":"read","arguments":{"path":"a"},"parameters":{"path":"b"}}',
     VALID, "read", {"path": "a"}),
    ("arguments_before_name", '{"arguments":{"path":"a.py"},"name":"read"}', VALID, "read", {"path": "a.py"}),
    ("python_tag", '<|python_tag|>{"name":"read","parameters":{"path":"a.py"}}', VALID, "read", {"path": "a.py"}),
    ("python_tag_eom", '<|python_tag|>{"name":"read","parameters":{"path":"a.py"}}<|eom_id|>',
     VALID, "read", {"path": "a.py"}),
    ("python_tag_eot", '<|python_tag|>{"name":"ls","parameters":{}}<|eot_id|>', VALID, "ls", {}),
    ("fence_json", '```json\n' + READ_A + '\n```', VALID, "read", {"path": "a.py"}),
    ("fence_plain", '```\n' + READ_A + '\n```', VALID, "read", {"path": "a.py"}),
    ("fence_upper_lang", '```JSON\n' + READ_A + '\n```', VALID, "read", {"path": "a.py"}),
    ("fence_one_line", '```' + READ_A + '```', VALID, "read", {"path": "a.py"}),
    ("fence_after_prose", 'Here is the call:\n```json\n' + READ_A + '\n```', VALID, "read", {"path": "a.py"}),
    ("fence_then_prose", '```json\n' + READ_A + '\n```\nThat reads it.', VALID, "read", {"path": "a.py"}),
    ("surrounding_whitespace", '\n\n   ' + READ_A + '   \n\n', VALID, "read", {"path": "a.py"}),
    ("crlf_lines", 'Calling:\r\n' + READ_A + '\r\n', VALID, "read", {"path": "a.py"}),
    ("prose_before_newline", 'I will read the file now.\n' + READ_A, VALID, "read", {"path": "a.py"}),
    ("prose_before_colon", 'Let me read it: ' + READ_A, VALID, "read", {"path": "a.py"}),
    ("prose_after", READ_A + '\nThis reads the file.', VALID, "read", {"path": "a.py"}),
    ("prose_both_sides", 'Reading: ' + READ_A + ' then I will edit.', VALID, "read", {"path": "a.py"}),
    ("trailing_semicolon", READ_A + ';', VALID, "read", {"path": "a.py"}),
    ("trailing_period", READ_A + '.', VALID, "read", {"path": "a.py"}),
    ("pretty_printed", json.dumps({"name": "read", "arguments": {"path": "a.py"}}, indent=2),
     VALID, "read", {"path": "a.py"}),
    # The OpenAI shapes, echoed back as text: the inner object is the call.
    ("wrapped_in_function", '{"function":{"name":"read","arguments":{"path":"a.py"}}}',
     VALID, "read", {"path": "a.py"}),
    ("openai_tool_call_echo",
     '{"id":"x","type":"function","function":{"name":"read","arguments":{"path":"a.py"}}}',
     VALID, "read", {"path": "a.py"}),
    ("array_of_one", '[' + READ_A + ']', VALID, "read", {"path": "a.py"}),
    # Only one call per turn is supported: the first wins and the rest are dropped.
    ("array_of_two_takes_first", '[' + READ_A + ',{"name":"ls","arguments":{}}]', VALID, "read", {"path": "a.py"}),
    ("two_objects_take_first", READ_A + '{"name":"ls","arguments":{}}', VALID, "read", {"path": "a.py"}),
    ("two_lines_take_first", READ_A + '\n{"name":"ls","arguments":{}}', VALID, "read", {"path": "a.py"}),
    ("unknown_first_known_second", '{"name":"upload","arguments":{}} ' + READ_A, VALID, "read", {"path": "a.py"}),
    ("data_objects_before_call", '{"a":1} {"b":2} {"c":3} {"d":4} {"e":5} ' + READ_A,
     VALID, "read", {"path": "a.py"}),
    ("brace_string_before_call", '{"x":"{"} ' + READ_A, VALID, "read", {"path": "a.py"}),
    ("no_arguments_key", '{"name":"ls"}', VALID, "ls", {}),
    ("empty_arguments", '{"name":"ls","arguments":{}}', VALID, "ls", {}),
    ("nested_list_arguments", '{"name":"edit","arguments":{"edits":[{"old":"a","new":"b"},{"old":"c","new":"d"}]}}',
     VALID, "edit", {"edits": [{"old": "a", "new": "b"}, {"old": "c", "new": "d"}]}),
    ("code_with_balanced_braces_in_prose",
     'Writing: {"name":"write","arguments":{"path":"m.c","content":"int main() { return 0; }"}} ok',
     VALID, "write", {"path": "m.c", "content": "int main() { return 0; }"}),
    ("unbalanced_brace_when_whole_text", '{"name":"write","arguments":{"content":"}"}}', VALID, "write", {"content": "}"}),
    # strict=False: Llama often writes a raw newline inside a JSON string.
    ("literal_newline_in_string", '{"name":"write","arguments":{"content":"a\nb"}}', VALID, "write", {"content": "a\nb"}),
    ("literal_tab_in_string", '{"name":"write","arguments":{"content":"a\tb"}}', VALID, "write", {"content": "a\tb"}),
    ("any_name_when_valid_is_none", '{"name":"anything","arguments":{"x":1}}', None, "anything", {"x": 1}),
    ("any_name_when_valid_is_empty", '{"name":"anything","arguments":{"x":1}}', set(), "anything", {"x": 1}),
    ("dotted_dashed_name", '{"name":"mcp.git-status","arguments":{}}', {"mcp.git-status"}, "mcp.git-status", {}),
    ("non_ascii_name", '{"name":"lire_fichier_é","arguments":{}}', {"lire_fichier_é"}, "lire_fichier_é", {}),
    ("name_inside_arguments_too", '{"name":"write","arguments":{"name":"read","path":"x"}}',
     VALID, "write", {"name": "read", "path": "x"}),
]

# (slug, model text, valid names)
PLAIN = [
    ("prose", "The file defines two functions.", VALID),
    ("whitespace_only", "   \n\t ", VALID),
    ("function_call_syntax", 'read(path="a.py")', VALID),
    ("python_tag_builtin_syntax", '<|python_tag|>brave_search.call(query="elm")', VALID),
    ("xml_function_tag", '<function=read>{"path": "a.py"}</function>', VALID),
    ("single_quoted_dict", "{'name': 'read', 'arguments': {'path': 'a.py'}}", VALID),
    ("unquoted_keys", '{name: "read", arguments: {path: "a.py"}}', VALID),
    ("unknown_tool", '{"name":"upload","arguments":{}}', VALID),
    ("name_case_differs", '{"name":"Read","arguments":{}}', VALID),
    ("name_with_space", '{"name":" read","arguments":{}}', VALID),
    ("name_null", '{"name":null,"arguments":{}}', VALID),
    ("name_empty", '{"name":"","arguments":{}}', None),
    ("name_number", '{"name":5,"arguments":{}}', VALID),
    ("trailing_comma", '{"name":"read","arguments":{"path":"a.py"},}', VALID),
    ("truncated", '{"name":"read","arguments":{"path":"a.py"}', VALID),
    ("js_comment", '{"name":"read", // the file\n "arguments":{}}', VALID),
    ("name_only_in_prose", 'The "name" field is required.', VALID),
    ("object_without_name", '{"tool":"read","args":{"path":"a.py"}}', VALID),
    ("call_escaped_inside_string", '{"text":"{\\"name\\": \\"read\\"}"}', VALID),
    ("instructions_template_echo", '{"name": "<function name>", "arguments": {...}}', VALID),
    ("python_code_fence", '```python\nperson = {"name": "bob"}\n```', VALID),
    ("array_of_strings", '["read", "write"]', VALID),
    ("stray_braces", "if a } b { c then", VALID),
    ("html_escaped_quotes", '{&quot;name&quot;:&quot;read&quot;}', VALID),
]


class ExtractCallTests(unittest.TestCase):
    """Text formats the shim turns into a call, and near-misses it must leave as prose."""

    @classmethod
    def setUpClass(cls):
        cls.shim = load_shim("elm_pi_shim_extract")

    def check_call(self, text, valid, name, arguments):
        calls, leftover = self.shim.extract_call(text, valid)
        self.assertIsNotNone(calls, text)
        self.assertEqual(1, len(calls))
        call = calls[0]
        self.assertEqual("", leftover)
        self.assertRegex(call["id"], CALL_ID)
        self.assertEqual("function", call["type"])
        self.assertEqual(name, call["function"]["name"])
        self.assertIsInstance(call["function"]["arguments"], str)
        self.assertEqual(canonical(arguments), canonical(json.loads(call["function"]["arguments"])))

    def check_plain(self, text, valid):
        # Left exactly as the model wrote it, fence and all.
        self.assertEqual((None, text), self.shim.extract_call(text, valid))

    def test_none_text_is_returned_unchanged(self):
        self.assertEqual((None, None), self.shim.extract_call(None, VALID))

    def test_empty_text_is_returned_unchanged(self):
        self.assertEqual((None, ""), self.shim.extract_call("", VALID))

    def test_each_call_gets_a_fresh_id(self):
        ids = {self.shim.extract_call(READ_A, VALID)[0][0]["id"] for _ in range(20)}
        self.assertEqual(20, len(ids))

    def test_string_arguments_are_passed_through_verbatim(self):
        # Already a JSON string: re-serialising would change the spacing pi sees.
        calls, _ = self.shim.extract_call('{"name":"read","arguments":"{ \\"path\\" : \\"a.py\\" }"}', VALID)
        self.assertEqual('{ "path" : "a.py" }', calls[0]["function"]["arguments"])

    def test_openai_string_arguments_inside_function_wrapper(self):
        calls, _ = self.shim.extract_call(
            '{"type":"function","function":{"name":"read","arguments":"{\\"path\\":\\"a.py\\"}"}}', VALID)
        self.assertEqual('{"path":"a.py"}', calls[0]["function"]["arguments"])

    def test_prose_around_a_call_is_dropped(self):
        calls, leftover = self.shim.extract_call("Sure! " + READ_A + " Then I'll summarise.", VALID)
        self.assertEqual("read", calls[0]["function"]["name"])
        self.assertEqual("", leftover)

    def test_fenced_prose_keeps_its_fence(self):
        text = "```\nplain words\n```"
        self.assertEqual((None, text), self.shim.extract_call(text, VALID))

    def test_unbalanced_brace_in_argument_after_prose(self):
        calls, _ = self.shim.extract_call('Sure: {"name":"write","arguments":{"content":"a}b"}} ok', VALID)
        self.assertIsNotNone(calls)
        self.assertEqual('{"content": "a}b"}', calls[0]["function"]["arguments"])

    def test_unbalanced_open_brace_in_argument_then_prose(self):
        calls, _ = self.shim.extract_call('{"name":"write","arguments":{"content":"if (x) {"}} done', VALID)
        self.assertIsNotNone(calls)
        self.assertEqual('{"content": "if (x) {"}', calls[0]["function"]["arguments"])

    def test_null_arguments_become_an_empty_object(self):
        calls, _ = self.shim.extract_call('{"name":"ls","arguments":null}', VALID)
        self.assertEqual("{}", calls[0]["function"]["arguments"])

    def test_list_name_is_prose_not_a_crash(self):
        text = '{"name":["read"],"arguments":{}}'
        self.assertEqual((None, text), self.shim.extract_call(text, VALID))


add_cases(ExtractCallTests, "recognises", RECOGNISED, ExtractCallTests.check_call)
add_cases(ExtractCallTests, "plain", PLAIN, ExtractCallTests.check_plain)


# =============================================================================
# argument fidelity: the arguments pi receives are the ones the model wrote
# =============================================================================

# (slug, the arguments object as the model wrote it, the value pi must get)
ARGUMENTS = [
    ("simple_string", '{"path":"a.py"}', {"path": "a.py"}),
    ("empty_string", '{"path":""}', {"path": ""}),
    ("string_one_stays_string", '{"n":"1"}', {"n": "1"}),
    ("int_one_stays_int", '{"n":1}', {"n": 1}),
    ("zero", '{"n":0}', {"n": 0}),
    ("negative", '{"n":-42}', {"n": -42}),
    ("float", '{"n":3.25}', {"n": 3.25}),
    ("float_one_stays_float", '{"n":1.0}', {"n": 1.0}),
    ("exponent", '{"n":1e3}', {"n": 1000.0}),
    ("big_int_exact", '{"n":12345678901234567890}', {"n": 12345678901234567890}),
    ("true_stays_bool", '{"b":true}', {"b": True}),
    ("false_stays_bool", '{"b":false}', {"b": False}),
    ("string_true_stays_string", '{"b":"true"}', {"b": "true"}),
    ("null_value", '{"x":null}', {"x": None}),
    ("empty_list", '{"xs":[]}', {"xs": []}),
    ("mixed_list", '{"xs":[1,"two",3.0,false,null]}', {"xs": [1, "two", 3.0, False, None]}),
    ("deep_nesting", '{"a":{"b":{"c":{"d":{"e":"f"}}}}}', {"a": {"b": {"c": {"d": {"e": "f"}}}}}),
    ("key_order_kept", '{"z":1,"a":2,"m":3}', {"z": 1, "a": 2, "m": 3}),
    ("empty_key", '{"":"v"}', {"": "v"}),
    ("raw_accented", '{"text":"café naïve"}', {"text": "café naïve"}),
    ("escaped_accented", '{"text":"caf\\u00e9"}', {"text": "café"}),
    ("raw_emoji", '{"text":"ok 🎉"}', {"text": "ok 🎉"}),
    ("surrogate_pair_escape", '{"text":"\\ud83d\\ude00"}', {"text": "😀"}),
    ("cjk", '{"text":"読み込み"}', {"text": "読み込み"}),
    ("rtl", '{"text":"مرحبا"}', {"text": "مرحبا"}),
    ("escaped_double_quote", '{"text":"say \\"hi\\""}', {"text": 'say "hi"'}),
    ("single_quote", '{"text":"it\'s"}', {"text": "it's"}),
    ("windows_path_backslashes", '{"path":"C:\\\\dir\\\\f.txt"}', {"path": "C:\\dir\\f.txt"}),
    ("escaped_newline", '{"text":"a\\nb"}', {"text": "a\nb"}),
    ("escaped_crlf", '{"text":"a\\r\\nb"}', {"text": "a\r\nb"}),
    ("nul_escape", '{"text":"a\\u0000b"}', {"text": "a\x00b"}),
    ("json_inside_string", '{"body":"{\\"k\\": [1, 2]}"}', {"body": '{"k": [1, 2]}'}),
    ("markdown_and_html", '{"text":"# T\\n<b>x</b> `y`"}', {"text": "# T\n<b>x</b> `y`"}),
    ("closing_tag_in_string", '{"text":"</function><|eot_id|>"}', {"text": "</function><|eot_id|>"}),
    ("long_string", '{"text":"' + "x" * 20000 + '"}', {"text": "x" * 20000}),
    ("multiline_shell", '{"command":"set -e\\ncd src && make 2>&1 | tail -n 5"}',
     {"command": "set -e\ncd src && make 2>&1 | tail -n 5"}),
]


class ArgumentFidelityTests(unittest.TestCase):
    """Strings stay strings, numbers stay numbers, and no character is lost."""

    @classmethod
    def setUpClass(cls):
        cls.shim = load_shim("elm_pi_shim_arguments")

    def check(self, arguments_text, expected):
        calls, _ = self.shim.extract_call('{"name":"write","arguments":' + arguments_text + '}', VALID)
        self.assertIsNotNone(calls)
        self.assertEqual(canonical(expected), canonical(json.loads(calls[0]["function"]["arguments"])))


add_cases(ArgumentFidelityTests, "arguments", ARGUMENTS, ArgumentFidelityTests.check)


# =============================================================================
# flatten_messages: the conversation as Llama sees it
# =============================================================================

NUDGE = ("If the task is not finished, emit the next function call as a single-line JSON object NOW. "
         "Do not describe the action - perform it. If the task is finished, give the final answer.")


def tool_call(name, arguments, cid="c1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": arguments}}


# (slug, messages in, messages out)
FLATTEN = [
    ("user_unchanged", [{"role": "user", "content": "hi"}], [{"role": "user", "content": "hi"}]),
    ("system_unchanged", [{"role": "system", "content": "be brief"}], [{"role": "system", "content": "be brief"}]),
    ("user_name_dropped", [{"role": "user", "content": "hi", "name": "rob"}], [{"role": "user", "content": "hi"}]),
    ("multimodal_user_kept",
     [{"role": "user", "content": [{"type": "text", "text": "look"}]}],
     [{"role": "user", "content": [{"type": "text", "text": "look"}]}]),
    ("plain_assistant_unchanged", [{"role": "assistant", "content": "done"}], [{"role": "assistant", "content": "done"}]),
    ("assistant_empty_tool_calls_key_dropped",
     [{"role": "assistant", "content": "ok", "tool_calls": []}], [{"role": "assistant", "content": "ok"}]),
    ("string_arguments_parsed",
     [{"role": "assistant", "content": None, "tool_calls": [tool_call("read", '{"path":"a.py"}')]}],
     [{"role": "assistant", "content": '{"name":"read","arguments":{"path":"a.py"}}'}]),
    ("object_arguments",
     [{"role": "assistant", "content": None, "tool_calls": [tool_call("read", {"path": "a.py"})]}],
     [{"role": "assistant", "content": '{"name":"read","arguments":{"path":"a.py"}}'}]),
    ("invalid_string_arguments_kept_as_string",
     [{"role": "assistant", "content": None, "tool_calls": [tool_call("read", "{oops")]}],
     [{"role": "assistant", "content": '{"name":"read","arguments":"{oops"}'}]),
    ("content_then_call",
     [{"role": "assistant", "content": "Reading.", "tool_calls": [tool_call("read", "{}")]}],
     [{"role": "assistant", "content": 'Reading.\n{"name":"read","arguments":{}}'}]),
    ("whitespace_content_stripped",
     [{"role": "assistant", "content": "  ", "tool_calls": [tool_call("ls", "{}")]}],
     [{"role": "assistant", "content": '{"name":"ls","arguments":{}}'}]),
    ("two_calls_one_per_line",
     [{"role": "assistant", "content": "", "tool_calls": [tool_call("ls", "{}"), tool_call("read", '{"path":"b"}', "c2")]}],
     [{"role": "assistant", "content": '{"name":"ls","arguments":{}}\n{"name":"read","arguments":{"path":"b"}}'}]),
    ("call_without_function",
     [{"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function"}]}],
     [{"role": "assistant", "content": '{"name":null,"arguments":null}'}]),
    ("tool_result_named",
     [{"role": "tool", "tool_call_id": "c1", "name": "read", "content": "print(1)"}],
     [{"role": "user", "content": "FUNCTION RESULT (read):\nprint(1)\n\n" + NUDGE}]),
    # pi does not name tool results, so most arrive as "function".
    ("tool_result_unnamed",
     [{"role": "tool", "tool_call_id": "c1", "content": "ok"}],
     [{"role": "user", "content": "FUNCTION RESULT (function):\nok\n\n" + NUDGE}]),
    ("tool_result_empty",
     [{"role": "tool", "tool_call_id": "c1", "content": ""}],
     [{"role": "user", "content": "FUNCTION RESULT (function):\n\n\n" + NUDGE}]),
    ("tool_result_missing_content",
     [{"role": "tool", "tool_call_id": "c1"}],
     [{"role": "user", "content": "FUNCTION RESULT (function):\n\n\n" + NUDGE}]),
    ("tool_result_multiline",
     [{"role": "tool", "name": "bash", "content": "line 1\nline 2\n"}],
     [{"role": "user", "content": "FUNCTION RESULT (bash):\nline 1\nline 2\n\n\n" + NUDGE}]),
    ("tool_result_null_content",
     [{"role": "tool", "tool_call_id": "c1", "content": None}],
     [{"role": "user", "content": "FUNCTION RESULT (function):\n\n\n" + NUDGE}]),
    ("whole_turn_in_order",
     [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
      {"role": "assistant", "content": None, "tool_calls": [tool_call("ls", "{}")]},
      {"role": "tool", "tool_call_id": "c1", "content": "a.py"},
      {"role": "assistant", "content": "There is a.py."}],
     [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
      {"role": "assistant", "content": '{"name":"ls","arguments":{}}'},
      {"role": "user", "content": "FUNCTION RESULT (function):\na.py\n\n" + NUDGE},
      {"role": "assistant", "content": "There is a.py."}]),
]


class FlattenMessagesTests(unittest.TestCase):
    """Prior tool calls and their results are rewritten as text Llama can read."""

    @classmethod
    def setUpClass(cls):
        cls.shim = load_shim("elm_pi_shim_flatten")

    def check(self, messages, expected):
        self.assertEqual(expected, self.shim.flatten_messages(messages))

    def test_input_messages_are_not_mutated(self):
        messages = [{"role": "user", "content": "u", "name": "rob"},
                    {"role": "assistant", "content": None, "tool_calls": [tool_call("ls", "{}")]}]
        before = json.dumps(messages)
        self.shim.flatten_messages(messages)
        self.assertEqual(before, json.dumps(messages))

    def test_flattened_call_is_parsed_back_by_extract_call(self):
        # The model sees its own earlier calls in exactly the form the shim accepts.
        out = self.shim.flatten_messages(
            [{"role": "assistant", "content": None, "tool_calls": [tool_call("read", '{"path":"a b.py"}')]}])
        calls, _ = self.shim.extract_call(out[0]["content"], VALID)
        self.assertEqual({"path": "a b.py"}, json.loads(calls[0]["function"]["arguments"]))


add_cases(FlattenMessagesTests, "flatten", FLATTEN, FlattenMessagesTests.check)


# =============================================================================
# tools_to_prompt: the tool list as a system block
# =============================================================================

def schema_lines(prompt):
    head = "one JSON schema per line:\n\n"
    body = prompt[prompt.index(head) + len(head):prompt.index("\n\nTo call a function")]
    return body.split("\n") if body else []


# (slug, tools, the schema lines expected in the prompt)
TOOL_PROMPTS = [
    ("wrapped_function",
     [{"type": "function", "function": {"name": "read", "description": "Read a file",
                                        "parameters": {"type": "object"}}}],
     ['{"name":"read","description":"Read a file","parameters":{"type":"object"}}']),
    ("bare_tool", [{"name": "ls", "description": "List", "parameters": {}}],
     ['{"name":"ls","description":"List","parameters":{}}']),
    ("missing_description", [{"function": {"name": "ls", "parameters": {}}}],
     ['{"name":"ls","description":"","parameters":{}}']),
    ("missing_parameters", [{"function": {"name": "ls", "description": "d"}}],
     ['{"name":"ls","description":"d","parameters":{}}']),
    ("null_function", [{"type": "function", "function": None}],
     ['{"name":null,"description":"","parameters":{}}']),
    ("extra_keys_dropped",
     [{"type": "function", "function": {"name": "ls", "description": "d", "parameters": {}, "strict": True}}],
     ['{"name":"ls","description":"d","parameters":{}}']),
    # str.format must not touch braces inside the inserted schemas.
    ("braces_in_description", [{"function": {"name": "ls", "description": "use {path} and {{x}}"}}],
     ['{"name":"ls","description":"use {path} and {{x}}","parameters":{}}']),
    ("order_kept",
     [{"function": {"name": "b"}}, {"function": {"name": "a"}}, {"function": {"name": "c"}}],
     ['{"name":"b","description":"","parameters":{}}', '{"name":"a","description":"","parameters":{}}',
      '{"name":"c","description":"","parameters":{}}']),
    ("no_tools", [], []),
]


class ToolsToPromptTests(unittest.TestCase):
    """Each tool becomes one compact JSON line inside the instructions."""

    @classmethod
    def setUpClass(cls):
        cls.shim = load_shim("elm_pi_shim_tools")

    def check(self, tools, expected):
        self.assertEqual(expected, schema_lines(self.shim.tools_to_prompt(tools)))

    def test_example_call_renders_with_single_braces(self):
        prompt = self.shim.tools_to_prompt([])
        self.assertIn('\n{"name": "<function name>", "arguments": {...}}\n', prompt)

    def test_newline_in_description_stays_on_one_line(self):
        lines = schema_lines(self.shim.tools_to_prompt([{"function": {"name": "ls", "description": "a\nb"}}]))
        self.assertEqual(['{"name":"ls","description":"a\\nb","parameters":{}}'], lines)


add_cases(ToolsToPromptTests, "tools", TOOL_PROMPTS, ToolsToPromptTests.check)


# =============================================================================
# _url: joining the upstream base and the client's path
# =============================================================================

# (slug, upstream base, client path, URL requested)
URLS = [
    ("strips_v1_chat", "https://elm.example/api/v1", "/v1/chat/completions", "https://elm.example/api/v1/chat/completions"),
    ("plain_chat", "https://elm.example/api/v1", "/chat/completions", "https://elm.example/api/v1/chat/completions"),
    ("strips_v1_models", "https://elm.example/api/v1", "/v1/models", "https://elm.example/api/v1/models"),
    ("bare_v1", "https://elm.example/api/v1", "/v1", "https://elm.example/api/v1/"),
    ("v1_slash", "https://elm.example/api/v1", "/v1/", "https://elm.example/api/v1/"),
    ("v1beta_not_stripped", "https://elm.example/api/v1", "/v1beta/x", "https://elm.example/api/v1/v1beta/x"),
    ("query_kept", "https://elm.example/api/v1", "/v1/models?limit=2", "https://elm.example/api/v1/models?limit=2"),
    ("base_trailing_slash", "https://elm.example/api/v1/", "/v1/models", "https://elm.example/api/v1/models"),
    ("base_without_v1", "https://elm.example/api", "/v1/models", "https://elm.example/api/v1/models"),
    ("base_v2_not_stripped", "https://elm.example/api/v2", "/v1/models", "https://elm.example/api/v2/v1/models"),
    ("only_one_v1_stripped", "https://elm.example/v1", "/v1/v1/x", "https://elm.example/v1/v1/x"),
]


class UrlTests(unittest.TestCase):
    """No doubled /v1 when pi appends its own /v1 to a base that has one."""

    @classmethod
    def setUpClass(cls):
        cls.shim = load_shim("elm_pi_shim_url")

    def check(self, upstream, path, expected):
        with mock.patch.object(self.shim, "UPSTREAM", upstream):
            self.assertEqual(expected, self.shim._url(path))


add_cases(UrlTests, "url", URLS, UrlTests.check)


# =============================================================================
# egress proxy discovery
# =============================================================================

class ProxyResolutionTests(unittest.TestCase):
    """The proxy is found per request, from the environment then live port files."""

    @classmethod
    def setUpClass(cls):
        cls.shim = load_shim("elm_pi_shim_proxy")
        cls.listener = socket.socket()
        cls.listener.bind(("127.0.0.1", 0))
        cls.listener.listen(16)
        cls.live = cls.listener.getsockname()[1]
        cls.other = socket.socket()
        cls.other.bind(("127.0.0.1", 0))
        cls.other.listen(16)
        cls.live2 = cls.other.getsockname()[1]
        cls.dead = closed_port()

    @classmethod
    def tearDownClass(cls):
        cls.listener.close()
        cls.other.close()

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for key in PROXY_VARS:
            os.environ.pop(key, None)
        glob = mock.patch.object(self.shim, "PROXY_GLOB", str(self.dir / "elm-pi-egress-*.port"))
        glob.start()
        self.addCleanup(glob.stop)
        self.shim._proxy_cached = None

    def port_file(self, name, content, age=0):
        path = self.dir / f"elm-pi-egress-{name}.port"
        path.write_text(content)
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))

    def test_accepting_live_url(self):
        self.assertTrue(self.shim._accepting(f"http://127.0.0.1:{self.live}"))

    def test_accepting_with_credentials_and_slash(self):
        self.assertTrue(self.shim._accepting(f"http://user:pw@127.0.0.1:{self.live}/"))

    def test_accepting_without_scheme(self):
        self.assertTrue(self.shim._accepting(f"127.0.0.1:{self.live}"))

    def test_accepting_empty_host_means_loopback(self):
        self.assertTrue(self.shim._accepting(f"http://:{self.live}"))

    def test_not_accepting_closed_port(self):
        self.assertFalse(self.shim._accepting(f"http://127.0.0.1:{self.dead}"))

    def test_not_accepting_url_without_port(self):
        self.assertFalse(self.shim._accepting("http://127.0.0.1"))

    def test_candidates_env_order_then_newest_file(self):
        os.environ.update({"http_proxy": "http://h4:4", "HTTPS_PROXY": "http://h1:1",
                           "HTTP_PROXY": "http://h3:3", "https_proxy": "http://h2:2"})
        self.port_file("old", "1111\n", age=100)
        self.port_file("new", "2222\n", age=1)
        self.assertEqual(["http://h1:1", "http://h2:2", "http://h3:3", "http://h4:4",
                          "http://127.0.0.1:2222", "http://127.0.0.1:1111"],
                         list(self.shim._proxy_candidates()))

    def test_candidates_skip_unreadable_port_files(self):
        self.port_file("junk", "not a port", age=1)
        self.port_file("empty", "", age=2)
        self.port_file("good", "  3333 \n", age=3)
        self.assertEqual(["http://127.0.0.1:3333"], list(self.shim._proxy_candidates()))

    def test_resolve_skips_dead_env_proxy_for_live_port_file(self):
        os.environ["HTTPS_PROXY"] = f"http://127.0.0.1:{self.dead}"
        self.port_file("s", str(self.live))
        self.assertEqual(f"http://127.0.0.1:{self.live}", self.shim.resolve_proxy())

    def test_resolve_none_when_nothing_answers(self):
        os.environ["HTTPS_PROXY"] = f"http://127.0.0.1:{self.dead}"
        self.assertIsNone(self.shim.resolve_proxy())

    def test_resolve_keeps_a_live_cached_proxy(self):
        self.port_file("a", str(self.live))
        first = self.shim.resolve_proxy()
        self.port_file("b", str(self.live2), age=-10)    # newer, but the cached one still answers
        self.assertEqual(first, self.shim.resolve_proxy())

    def test_resolve_force_rereads(self):
        self.port_file("a", str(self.live), age=10)
        self.shim.resolve_proxy()
        self.port_file("b", str(self.live2))
        self.assertEqual(f"http://127.0.0.1:{self.live2}", self.shim.resolve_proxy(force=True))

    def test_resolve_drops_a_dead_cached_proxy(self):
        self.shim._proxy_cached = f"http://127.0.0.1:{self.dead}"
        self.port_file("a", str(self.live))
        self.assertEqual(f"http://127.0.0.1:{self.live}", self.shim.resolve_proxy())

    def opener_proxies(self, opener):
        return [h.proxies for h in opener.handlers if type(h).__name__ == "ProxyHandler"]

    def test_unmanaged_opener_goes_direct(self):
        # No proxy handler at all - not even urllib's default one that reads HTTPS_PROXY.
        os.environ["HTTPS_PROXY"] = f"http://127.0.0.1:{self.live}"
        with mock.patch.object(self.shim, "PROXY_MANAGED", False):
            self.assertEqual([], self.opener_proxies(self.shim._build_opener()))

    def test_managed_opener_uses_live_proxy(self):
        self.port_file("a", str(self.live))
        url = f"http://127.0.0.1:{self.live}"
        with mock.patch.object(self.shim, "PROXY_MANAGED", True):
            self.assertEqual([{"http": url, "https": url}], self.opener_proxies(self.shim._build_opener()))

    def test_managed_without_proxy_refuses_to_go_direct(self):
        with mock.patch.object(self.shim, "PROXY_MANAGED", True):
            with self.assertRaisesRegex(RuntimeError, "no live elm-pi egress proxy"):
                self.shim._build_opener()


# =============================================================================
# HTTP: what the shim sends upstream for a shimmed request
# =============================================================================

def first(messages):
    return messages[0]


# (slug, request fields (merged over a Llama request with TOOLS), what to read from the upstream body, expected)
REWRITES = [
    ("tools_removed", {}, lambda up: "tools" in up, False),
    ("tool_choice_removed", {"tool_choice": "auto"}, lambda up: "tool_choice" in up, False),
    ("parallel_tool_calls_removed", {"parallel_tool_calls": True}, lambda up: "parallel_tool_calls" in up, False),
    ("stream_options_removed", {"stream": True, "stream_options": {"include_usage": True}},
     lambda up: "stream_options" in up, False),
    ("stream_forced_off", {"stream": True}, lambda up: up["stream"], False),
    ("temperature_zero_overrides_client", {"temperature": 0.6}, lambda up: up["temperature"], 0.0),
    ("max_tokens_kept", {"max_tokens": 8192}, lambda up: up["max_tokens"], 8192),
    ("top_p_kept", {"top_p": 0.9}, lambda up: up["top_p"], 0.9),
    ("model_kept", {}, lambda up: up["model"], LLAMA),
    ("system_inserted_first", {}, lambda up: [m["role"] for m in up["messages"]], ["system", "user"]),
    ("system_block_lists_tools", {},
     lambda up: schema_lines(first(up["messages"])["content"])[0][:15], '{"name":"read",'),
    ("system_merged_with_existing",
     {"messages": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "hi"}]},
     lambda up: (len(up["messages"]), first(up["messages"])["content"].split("\n\n")[0]), (2, "Be brief.")),
    ("developer_becomes_system",
     {"messages": [{"role": "developer", "content": "Dev."}, {"role": "user", "content": "hi"}]},
     lambda up: (first(up["messages"])["role"], first(up["messages"])["content"][:6]), ("system", "Dev.\n\n")),
    ("null_system_content_merged",
     {"messages": [{"role": "system", "content": None}, {"role": "user", "content": "hi"}]},
     lambda up: first(up["messages"])["content"][:20], "\n\nYou can call funct"),
    ("later_system_left_alone",
     {"messages": [{"role": "user", "content": "hi"}, {"role": "system", "content": "late"}]},
     lambda up: up["messages"][2], {"role": "system", "content": "late"}),
    ("tool_history_flattened",
     {"messages": [{"role": "user", "content": "list"},
                   {"role": "assistant", "content": None, "tool_calls": [tool_call("ls", "{}")]},
                   {"role": "tool", "tool_call_id": "c1", "content": "a.py"}]},
     lambda up: [m["role"] for m in up["messages"]] + [up["messages"][2]["content"]],
     ["system", "user", "assistant", "user", '{"name":"ls","arguments":{}}']),
    ("no_tool_keys_left_in_messages",
     {"messages": [{"role": "assistant", "content": None, "tool_calls": [tool_call("ls", "{}")]},
                   {"role": "tool", "tool_call_id": "c1", "name": "ls", "content": "x"}]},
     lambda up: sorted({k for m in up["messages"] for k in m}), ["content", "role"]),
    ("unknown_fields_forwarded", {"seed": 7, "stop": ["\n\n"]}, lambda up: (up["seed"], up["stop"]), (7, ["\n\n"])),
]


class ShimRequestTests(ShimServerCase):
    """A Llama request with tools reaches ELM as a plain chat with the tools in the prompt."""

    def check(self, fields, read, expected):
        self.reply_with(completion("ok"))
        status, _, _ = self.chat(fields)
        self.assertEqual(200, status)
        self.assertEqual(expected, read(self.sent()))

    def test_temperature_from_environment(self):
        self.reply_with(completion("ok"))
        with mock.patch.dict(os.environ, {"SHIM_TEMPERATURE": "0.3"}):
            self.chat({"temperature": 0.9})
        self.assertEqual(0.3, self.sent()["temperature"])

    def test_upstream_path_for_v1_client_path(self):
        self.reply_with(completion("ok"))
        self.chat({}, path="/v1/chat/completions")
        self.assertEqual("/api/v1/chat/completions", self.upstream.requests[0]["path"])

    def test_upstream_path_ignores_client_query(self):
        # The shimmed branch always posts to the base's /chat/completions.
        self.reply_with(completion("ok"))
        self.chat({}, path="/chat/completions?trace=1")
        self.assertEqual("/api/v1/chat/completions", self.upstream.requests[0]["path"])

    def test_authorization_forwarded(self):
        self.reply_with(completion("ok"))
        self.chat({}, headers={"Authorization": "Bearer test-key"})
        self.assertEqual("Bearer test-key", self.upstream.requests[0]["headers"]["authorization"])

    def test_custom_header_forwarded(self):
        self.reply_with(completion("ok"))
        self.chat({}, headers={"X-Trace": "abc"})
        self.assertEqual("abc", self.upstream.requests[0]["headers"]["x-trace"])

    def test_host_is_upstreams_not_shims(self):
        self.reply_with(completion("ok"))
        self.chat({})
        self.assertEqual(f"127.0.0.1:{self.upstream.port}", self.upstream.requests[0]["headers"]["host"])

    def test_client_gzip_not_forwarded(self):
        # The shim parses the reply itself; a compressed one would not be JSON.
        self.reply_with(completion("ok"))
        self.chat({}, headers={"Accept-Encoding": "gzip"})
        self.assertEqual("identity", self.upstream.requests[0]["headers"].get("accept-encoding"))

    def test_content_length_matches_rewritten_body(self):
        self.reply_with(completion("ok"))
        self.chat({})
        sent = self.upstream.requests[0]
        self.assertEqual(str(len(sent["body"])), sent["headers"]["content-length"])

    def test_eurollm_is_shimmed(self):
        self.reply_with(completion("ok"))
        self.chat({"model": EUROLLM})
        self.assertNotIn("tools", self.sent())

    def test_model_with_suffix_is_shimmed(self):
        self.reply_with(completion("ok"))
        self.chat({"model": LLAMA + "-FP8"})
        self.assertNotIn("tools", self.sent())


add_cases(ShimRequestTests, "rewrite", REWRITES, ShimRequestTests.check)


# =============================================================================
# HTTP: which requests are passed through untouched
# =============================================================================

# (slug, path, request body) - each must reach upstream byte for byte
PASSTHROUGH = [
    ("qwen_with_tools", "/v1/chat/completions", {"model": QWEN, "tools": TOOLS, "messages": []}),
    ("llama_without_tools", "/v1/chat/completions", {"model": LLAMA, "messages": [{"role": "user", "content": "hi"}]}),
    ("llama_empty_tools", "/v1/chat/completions", {"model": LLAMA, "tools": [], "messages": []}),
    ("llama_tools_on_completions_endpoint", "/v1/completions", {"model": LLAMA, "tools": TOOLS, "prompt": "x"}),
    ("model_case_differs", "/v1/chat/completions", {"model": LLAMA.lower(), "tools": TOOLS, "messages": []}),
    ("provider_prefixed_model", "/v1/chat/completions", {"model": "elm-shim/" + LLAMA, "tools": TOOLS, "messages": []}),
    ("embeddings", "/v1/embeddings", {"model": LLAMA, "input": "x"}),
]


class PassthroughTests(ShimServerCase):
    """Everything that does not need the shim goes to ELM exactly as sent."""

    def check(self, path, body):
        raw = json.dumps(body, separators=(",", ":")).encode()
        self.reply_with(b'{"passed":true}', ctype="application/json; charset=utf-8")
        status, headers, reply = self.request("POST", path, raw)
        self.assertEqual((200, b'{"passed":true}'), (status, reply))
        self.assertEqual("application/json; charset=utf-8", headers["content-type"])
        self.assertEqual(raw, self.upstream.requests[0]["body"])
        self.assertEqual("/api/v1" + path[len("/v1"):], self.upstream.requests[0]["path"])

    def test_invalid_json_body_forwarded_raw(self):
        self.reply_with(b"{}")
        self.request("POST", "/v1/chat/completions", b"not json {")
        self.assertEqual(b"not json {", self.upstream.requests[0]["body"])

    def test_get_forwarded_with_query(self):
        self.reply_with({"data": [{"id": LLAMA}]})
        status, _, body = self.request("GET", "/v1/models?x=1")
        self.assertEqual((200, {"data": [{"id": LLAMA}]}), (status, json.loads(body)))
        self.assertEqual(("GET", "/api/v1/models?x=1"),
                         (self.upstream.requests[0]["method"], self.upstream.requests[0]["path"]))

    def test_get_error_status_forwarded(self):
        self.reply_with({"error": "no"}, status=404)
        status, _, body = self.request("GET", "/v1/nothing")
        self.assertEqual((404, {"error": "no"}), (status, json.loads(body)))

    def test_post_error_status_forwarded(self):
        self.reply_with({"error": {"message": "bad key"}}, status=401)
        status, _, body = self.request("POST", "/v1/chat/completions", {"model": QWEN, "messages": []})
        self.assertEqual((401, "bad key"), (status, json.loads(body)["error"]["message"]))

    def test_streaming_passthrough_is_byte_identical_and_chunked(self):
        stream = b"".join(b'data: {"i":%d,"pad":"%s"}\n\n' % (i, b"x" * 300) for i in range(20)) + b"data: [DONE]\n\n"
        self.reply_with(stream, ctype="text/event-stream")
        status, headers, body = self.request("POST", "/v1/chat/completions",
                                             {"model": QWEN, "stream": True, "messages": []})
        self.assertEqual((200, "chunked", "text/event-stream", stream),
                         (status, headers.get("transfer-encoding"), headers["content-type"], body))

    def test_health_is_answered_only_for_get(self):
        self.reply_with(b'{"upstream":true}')
        status, _, body = self.request("POST", self.shim.HEALTH_PATH, b"{}")
        self.assertEqual(b'{"upstream":true}', body)
        self.assertEqual("/api/v1" + self.shim.HEALTH_PATH, self.upstream.requests[0]["path"])


add_cases(PassthroughTests, "passthrough", PASSTHROUGH, PassthroughTests.check)


class HealthTests(ShimServerCase):
    """The health endpoint identifies this shim and is never forwarded."""

    def health(self, path=None):
        status, _, body = self.request("GET", path or self.shim.HEALTH_PATH)
        self.assertEqual(200, status)
        return json.loads(body)

    def test_identifies_as_elm_pi(self):
        self.assertEqual("elm-pi", self.health()["shim"])

    def test_reports_pid_port_and_upstream(self):
        body = self.health()
        self.assertEqual((os.getpid(), self.port, f"http://127.0.0.1:{self.upstream.port}/api/v1"),
                         (body["pid"], body["port"], body["upstream"]))

    def test_reports_shimmed_models(self):
        self.assertEqual([LLAMA, EUROLLM], self.health()["models"])

    def test_unmanaged_reports_no_proxy(self):
        body = self.health()
        self.assertEqual((False, None, ""), (body["proxyManaged"], body["proxy"], body["proxyFromEnv"]))

    def test_query_string_still_health(self):
        self.assertEqual("elm-pi", self.health(self.shim.HEALTH_PATH + "?probe=1")["shim"])
        self.assertEqual([], self.upstream.requests)


# =============================================================================
# HTTP: what pi gets back from a shimmed request
# =============================================================================

def message_of(body):
    return body["choices"][0]["message"]


# (slug, upstream completion, request fields, read from the reply, expected)
RESPONSES = [
    ("call_becomes_tool_calls", completion(READ_A), {},
     lambda b: (message_of(b)["content"], message_of(b)["tool_calls"][0]["function"]),
     (None, {"name": "read", "arguments": '{"path": "a.py"}'})),
    ("call_finish_reason", completion(READ_A), {}, lambda b: b["choices"][0]["finish_reason"], "tool_calls"),
    ("call_after_length_is_tool_calls", completion(READ_A, finish="length"), {},
     lambda b: b["choices"][0]["finish_reason"], "tool_calls"),
    ("call_id_shape", completion(READ_A), {},
     lambda b: bool(CALL_ID.match(message_of(b)["tool_calls"][0]["id"])), True),
    ("python_tag_call", completion('<|python_tag|>{"name":"bash","parameters":{"command":"ls"}}'), {},
     lambda b: message_of(b)["tool_calls"][0]["function"], {"name": "bash", "arguments": '{"command": "ls"}'}),
    ("text_is_content", completion("All done."), {},
     lambda b: message_of(b), {"role": "assistant", "content": "All done."}),
    ("text_finish_stop", completion("All done."), {}, lambda b: b["choices"][0]["finish_reason"], "stop"),
    ("text_keeps_length", completion("Trunc", finish="length"), {}, lambda b: b["choices"][0]["finish_reason"], "length"),
    ("text_missing_finish_is_stop",
     {"id": "x", "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}}]}, {},
     lambda b: b["choices"][0]["finish_reason"], "stop"),
    # Tool names come from this request's tools: a call to one it did not offer is prose.
    ("unoffered_tool_is_text", completion('{"name":"write","arguments":{}}'), {},
     lambda b: message_of(b), {"role": "assistant", "content": '{"name":"write","arguments":{}}'}),
    ("bare_tool_names_count", completion('{"name":"ls","arguments":{}}'),
     {"tools": [{"name": "ls", "parameters": {}}]},
     lambda b: message_of(b)["tool_calls"][0]["function"]["name"], "ls"),
    ("fenced_text_kept_verbatim", completion("```\ncode\n```"), {},
     lambda b: message_of(b)["content"], "```\ncode\n```"),
    ("null_content_is_empty", completion(None), {}, lambda b: message_of(b), {"role": "assistant", "content": ""}),
    ("null_message_is_empty",
     {"id": "x", "choices": [{"index": 0, "message": None, "finish_reason": "stop"}]}, {},
     lambda b: message_of(b), {"role": "assistant", "content": ""}),
    ("no_choices_is_empty", {"id": "x", "choices": []}, {},
     lambda b: (message_of(b), b["choices"][0]["finish_reason"]), ({"role": "assistant", "content": ""}, "stop")),
    ("extra_choices_dropped",
     {"id": "x", "choices": [{"index": 0, "message": {"role": "assistant", "content": "a"}, "finish_reason": "stop"},
                             {"index": 1, "message": {"role": "assistant", "content": "b"}, "finish_reason": "stop"}]},
     {}, lambda b: [c["message"]["content"] for c in b["choices"]], ["a"]),
    ("upstream_message_extras_dropped",
     {"id": "x", "choices": [{"index": 0, "finish_reason": "stop",
                              "message": {"role": "assistant", "content": "a", "refusal": None,
                                          "reasoning_content": "think"}}]},
     {}, lambda b: sorted(message_of(b)), ["content", "role"]),
    ("envelope_kept", completion("hi"), {},
     lambda b: (b["id"], b["created"], b["model"], b["usage"]["total_tokens"]),
     ("chatcmpl-up1", 1700000000, LLAMA, 18)),
]


class ShimResponseTests(ShimServerCase):
    """The model's text comes back as an OpenAI reply, with a tool call when it made one."""

    def check(self, upstream, fields, read, expected):
        self.reply_with(upstream)
        status, headers, body = self.chat(fields)
        self.assertEqual((200, "application/json"), (status, headers["content-type"]))
        self.assertEqual(expected, read(json.loads(body)))

    def test_upstream_error_body_becomes_400(self):
        error = {"error": {"message": "context too long", "code": 400}}
        self.reply_with(error)
        status, _, body = self.chat({})
        self.assertEqual((400, error), (status, json.loads(body)))

    def test_upstream_http_error_forwarded(self):
        self.reply_with({"error": {"message": "rate limited"}}, status=429)
        status, _, body = self.chat({})
        self.assertEqual((429, "rate limited"), (status, json.loads(body)["error"]["message"]))

    def test_upstream_500_forwarded(self):
        self.reply_with(b"boom", status=500, ctype="text/plain")
        status, _, body = self.chat({})
        self.assertEqual((500, b"boom"), (status, body))

    def test_upstream_not_json_is_502(self):
        self.reply_with(b"<html>gateway</html>", ctype="text/html")
        status, _, body = self.chat({})
        self.assertEqual(502, status)
        self.assertIn("message", json.loads(body)["error"])

    def test_upstream_down_is_502(self):
        with mock.patch.object(self.shim, "UPSTREAM", f"http://127.0.0.1:{closed_port()}/api/v1"):
            status, _, body = self.chat({})
        self.assertEqual(502, status)
        self.assertRegex(json.loads(body)["error"]["message"], "(?i)refused")

    def test_upstream_json_array_is_502(self):
        self.reply_with(b"[]")
        status, _, _ = self.chat({})
        self.assertEqual(502, status)

    def test_upstream_choice_of_wrong_shape_is_502(self):
        for reply in (b'{"choices": [1]}', b'{"choices": {"message": {}}}',
                      b'{"choices": [{"message": "hi"}]}', b'{"choices": [{"message": {"content": ["hi"]}}]}'):
            self.reply_with(reply)
            status, _, body = self.chat({})
            self.assertEqual((502, reply), (status, reply))
            self.assertIn("usable choice", json.loads(body)["error"]["message"])

    def test_list_name_from_model_is_text(self):
        self.reply_with(completion('{"name":["read"],"arguments":{}}'))
        status, _, body = self.chat({})
        self.assertEqual((200, '{"name":["read"],"arguments":{}}'), (status, message_of(json.loads(body))["content"]))


add_cases(ShimResponseTests, "response", RESPONSES, ShimResponseTests.check)


# =============================================================================
# HTTP: streaming clients get a single-shot SSE stream
# =============================================================================

class ShimStreamingTests(ShimServerCase):
    """pi always streams; the buffered reply is re-emitted as chunks."""

    def stream(self, upstream):
        self.reply_with(upstream)
        status, headers, body = self.chat({"stream": True})
        self.assertEqual(200, status)
        events = sse_events(body)
        self.assertEqual("[DONE]", events[-1])
        return headers, [json.loads(e) for e in events[:-1]]

    def test_headers(self):
        headers, _ = self.stream(completion("hi"))
        self.assertEqual(("text/event-stream", "no-cache", "chunked"),
                         (headers["content-type"], headers["cache-control"], headers["transfer-encoding"]))

    def test_call_chunk_sequence(self):
        _, chunks = self.stream(completion(READ_A))
        deltas = [(c["choices"][0]["delta"], c["choices"][0]["finish_reason"]) for c in chunks]
        call = deltas[1][0]["tool_calls"][0]
        self.assertEqual({"role": "assistant", "content": ""}, deltas[0][0])
        self.assertEqual((0, "function", {"name": "read", "arguments": '{"path": "a.py"}'}),
                         (call["index"], call["type"], call["function"]))
        self.assertRegex(call["id"], CALL_ID)
        self.assertEqual([None, None, "tool_calls", None], [d[1] for d in deltas])

    def test_text_chunk_sequence(self):
        _, chunks = self.stream(completion("Here you go."))
        self.assertEqual([({"role": "assistant", "content": ""}, None), ({"content": "Here you go."}, None),
                          ({}, "stop"), ({}, None)],
                         [(c["choices"][0]["delta"], c["choices"][0]["finish_reason"]) for c in chunks])

    def test_chunks_carry_upstream_id_and_request_model(self):
        _, chunks = self.stream(completion("x", model="served-name"))
        self.assertEqual({("chatcmpl-up1", "chat.completion.chunk", 1700000000, LLAMA)},
                         {(c["id"], c["object"], c["created"], c["model"]) for c in chunks})

    def test_missing_upstream_id_gets_placeholder(self):
        _, chunks = self.stream({"created": 5, "choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]})
        self.assertEqual({"chatcmpl-shim"}, {c["id"] for c in chunks})

    def test_last_chunk_carries_usage(self):
        _, chunks = self.stream(completion("x"))
        self.assertEqual({"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}, chunks[-1]["usage"])

    def test_usage_null_when_upstream_has_none(self):
        body = completion("x")
        del body["usage"]
        _, chunks = self.stream(body)
        self.assertIsNone(chunks[-1]["usage"])

    def test_unicode_content_survives_stream(self):
        _, chunks = self.stream(completion("naïve 🎉 読み"))
        self.assertEqual("naïve 🎉 読み", chunks[1]["choices"][0]["delta"]["content"])

    def test_upstream_error_is_plain_json_not_sse(self):
        self.reply_with({"error": {"message": "nope"}})
        status, headers, body = self.chat({"stream": True})
        self.assertEqual((400, "application/json", "nope"),
                         (status, headers["content-type"], json.loads(body)["error"]["message"]))

    def test_length_finish_survives_streaming(self):
        _, chunks = self.stream(completion("Trunc", finish="length"))
        self.assertEqual("length", chunks[2]["choices"][0]["finish_reason"])


# =============================================================================
# HTTP: routed through a (fake) egress proxy found from a port file
# =============================================================================

class ProxyRoutingTests(ShimServerCase):
    """With a managed proxy, every upstream request goes through it; with none, nothing goes out."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dir = Path(tempfile.mkdtemp())
        cls.shim.PROXY_MANAGED = True
        # Never resolved: the fake proxy answers for it.
        cls.shim.UPSTREAM = "http://elm.invalid/api/v1"
        cls.shim.PROXY_GLOB = str(cls.dir / "elm-pi-egress-*.port")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        super().setUp()
        for path in self.dir.glob("*"):
            path.unlink()
        self.shim._proxy_cached = None

    def test_request_goes_through_proxy_from_port_file(self):
        (self.dir / "elm-pi-egress-1.port").write_text(str(self.upstream.port))
        self.reply_with(completion(READ_A))
        status, _, body = self.chat({})
        self.assertEqual((200, "tool_calls"), (status, json.loads(body)["choices"][0]["finish_reason"]))
        self.assertEqual("http://elm.invalid/api/v1/chat/completions", self.upstream.requests[0]["path"])

    def test_health_reports_resolved_proxy(self):
        (self.dir / "elm-pi-egress-1.port").write_text(str(self.upstream.port))
        _, _, body = self.request("GET", self.shim.HEALTH_PATH)
        body = json.loads(body)
        self.assertEqual((True, f"http://127.0.0.1:{self.upstream.port}"), (body["proxyManaged"], body["proxy"]))

    def test_no_live_proxy_is_502_not_direct(self):
        (self.dir / "elm-pi-egress-1.port").write_text(str(closed_port()))
        status, _, body = self.chat({})
        self.assertEqual(502, status)
        self.assertIn("no live elm-pi egress proxy", json.loads(body)["error"]["message"])
        self.assertEqual([], self.upstream.requests)


# =============================================================================
# the real script, started as elm-shim.ts starts it
# =============================================================================

class StandaloneShimTests(unittest.TestCase):
    """`python3 -E -S shim.py` starts with only the stdlib and listens on loopback only."""

    @classmethod
    def setUpClass(cls):
        cls.upstream = FakeUpstream()
        cls.dir = Path(tempfile.mkdtemp())
        cls.port = free_port()
        cls.base = f"http://127.0.0.1:{cls.upstream.port}/api/v1"
        env = {k: v for k, v in os.environ.items() if k not in PROXY_VARS}
        env.update({"SHIM_PORT": str(cls.port), "ELM_BASE_URL": cls.base, "TMPDIR": str(cls.dir),
                    "SHIM_MODELS": "x/a,,x/b"})
        cls.stderr = open(cls.dir / "stderr", "w+")
        cls.proc = subprocess.Popen([sys.executable, "-E", "-S", str(SHIM)], env=env,
                                    stdout=subprocess.DEVNULL, stderr=cls.stderr)
        cls.health = None
        deadline = time.time() + 30
        while time.time() < deadline and cls.proc.poll() is None:
            try:
                conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=2)
                conn.request("GET", "/__elm_shim__/health")
                cls.health = json.loads(conn.getresponse().read())
                conn.close()
                break
            except OSError:
                time.sleep(0.1)
        if cls.health is None:
            cls.tearDownClass()
            raise AssertionError("shim.py did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(10)
        cls.stderr.close()
        cls.upstream.stop()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_models_from_environment_without_blanks(self):
        self.assertEqual(["x/a", "x/b"], self.health["models"])

    def test_upstream_and_port_from_environment(self):
        self.assertEqual((self.base, self.port, self.proc.pid),
                         (self.health["upstream"], self.health["port"], self.health["pid"]))

    def test_not_proxy_managed_without_https_proxy(self):
        self.assertEqual((False, None), (self.health["proxyManaged"], self.health["proxy"]))

    def test_banner_names_loopback_address(self):
        self.stderr.seek(0)
        self.assertEqual(f"elm-tool-shim on 127.0.0.1:{self.port} -> {self.base}\n  shimming: x/a, x/b",
                         self.stderr.read().strip())

    def test_shims_models_named_in_environment(self):
        self.upstream.requests.clear()
        self.upstream.reply = (200, "application/json", json.dumps(completion('{"name":"ls"}')).encode())
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        conn.request("POST", "/v1/chat/completions", json.dumps(
            {"model": "x/b", "messages": [], "tools": [{"name": "ls"}]}))
        body = json.loads(conn.getresponse().read())
        conn.close()
        self.assertEqual("ls", body["choices"][0]["message"]["tool_calls"][0]["function"]["name"])
        self.assertNotIn("tools", json.loads(self.upstream.requests[0]["body"]))

    def test_listens_on_loopback_only(self):
        lsof = shutil.which("lsof")
        if not lsof:
            raise unittest.SkipTest("needs lsof")
        out = subprocess.run([lsof, "-nP", "-a", "-p", str(self.proc.pid), "-iTCP", "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=30).stdout
        addresses = re.findall(r"TCP (\S+) \(LISTEN\)", out)
        self.assertEqual([f"127.0.0.1:{self.port}"], addresses)


# =============================================================================
# elm-shim.ts: the provider it registers, under node with a stub pi
# =============================================================================

def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


# Imports the extension once per scenario (a fresh module each time, because it
# reads its environment at import) and records what it registers.
RUNNER = r"""
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const [source, scenariosFile] = process.argv.slice(1);
const scenarios = JSON.parse(readFileSync(scenariosFile, "utf8"));
const KEYS = ["ELM_SHIM_PORT", "ELM_SHIM_PATH", "ELM_LLAMA_MODEL_ID", "PI_CODING_AGENT_DIR", "ELM_PI_PYTHON"];
const out = {};
for (const [name, env] of Object.entries(scenarios)) {
  for (const key of KEYS) delete process.env[key];
  Object.assign(process.env, env);
  const mod = await import(pathToFileURL(source).href + "?" + name);
  const providers = [], notes = [], handlers = {};
  await mod.default({
    registerProvider: (id, config) => providers.push({ id, config }),
    on: (event, handler) => { handlers[event] = handler; },
  });
  if (handlers.session_start) {
    await handlers.session_start({}, { ui: { notify: (message, level) => notes.push({ message, level }) } });
  }
  out[name] = { providers, notes, events: Object.keys(handlers) };
}
console.log(JSON.stringify(out));
"""


class HealthStub(http.server.ThreadingHTTPServer):
    """Answers GET /__elm_shim__/health with a fixed status and body."""
    daemon_threads = True

    def __init__(self, status, body):
        stub = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                payload = json.dumps(body).encode()
                self.send_response(stub.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        super().__init__(("127.0.0.1", 0), H)
        self.status = status
        threading.Thread(target=self.serve_forever, daemon=True).start()


class ElmShimExtensionTests(unittest.TestCase):
    """elm-shim.ts registers the provider only when its own shim answers."""

    @classmethod
    def setUpClass(cls):
        cls.binary = node()
        if not cls.binary:
            raise unittest.SkipTest("needs node (run bootstrap.sh)")
        cls.dir = Path(tempfile.mkdtemp())
        cls.stubs = []
        cls.spawned_port = None
        try:
            cls._run()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _run(cls):
        (cls.dir / "package.json").write_text('{"type": "module"}')
        shutil.copy(EXTENSION, cls.dir / "elm-shim.ts")
        # A path no process has on its command line: pgrep -f must find nothing to stop.
        missing = str(cls.dir / "no-such" / "shim.py")
        healthy = HealthStub(200, {"shim": "elm-pi"})
        foreign = HealthStub(200, {"shim": "someone-else"})
        failing = HealthStub(500, {"shim": "elm-pi"})
        cls.stubs = [healthy, foreign, failing]
        # The extension starts a copy of the real shim on this port.
        shim_copy = cls.dir / "spawn" / "shim.py"
        shim_copy.parent.mkdir()
        shutil.copy(SHIM, shim_copy)
        cls.upstream = FakeUpstream()
        cls.spawned_port = free_port()
        cls.ports = {"healthy": healthy.server_address[1], "foreign": foreign.server_address[1],
                     "failing": failing.server_address[1], "absent": closed_port()}
        scenarios = {
            "healthy": {"ELM_SHIM_PORT": str(cls.ports["healthy"]), "ELM_SHIM_PATH": missing,
                        "ELM_LLAMA_MODEL_ID": LLAMA},
            "template": {"ELM_SHIM_PORT": str(cls.ports["healthy"]), "ELM_SHIM_PATH": missing},
            "foreign": {"ELM_SHIM_PORT": str(cls.ports["foreign"]), "ELM_SHIM_PATH": missing},
            "failing": {"ELM_SHIM_PORT": str(cls.ports["failing"]), "ELM_SHIM_PATH": missing},
            "absent": {"ELM_SHIM_PORT": str(cls.ports["absent"]), "ELM_SHIM_PATH": missing},
            "agentdir": {"ELM_SHIM_PORT": str(cls.ports["absent"]), "PI_CODING_AGENT_DIR": "/nowhere/agent"},
            "spawn": {"ELM_SHIM_PORT": str(cls.spawned_port), "ELM_SHIM_PATH": str(shim_copy),
                      "ELM_PI_PYTHON": sys.executable, "ELM_LLAMA_MODEL_ID": LLAMA},
        }
        scenarios_file = cls.dir / "scenarios.json"
        scenarios_file.write_text(json.dumps(scenarios))
        env = {k: v for k, v in os.environ.items() if k not in PROXY_VARS}
        env.update({"ELM_BASE_URL": f"http://127.0.0.1:{cls.upstream.port}/api/v1", "TMPDIR": str(cls.dir)})
        run = subprocess.run([cls.binary, "--no-warnings", "--input-type=module", "-e", RUNNER,
                              str(cls.dir / "elm-shim.ts"), str(scenarios_file)],
                             cwd=cls.dir, capture_output=True, text=True, env=env, timeout=120)
        if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
            raise unittest.SkipTest("this node cannot load TypeScript")
        if run.returncode != 0:
            raise AssertionError(run.stderr)
        cls.out = json.loads(run.stdout)
        cls.spawned = cls._health(cls.spawned_port)

    @staticmethod
    def _health(port):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request("GET", "/__elm_shim__/health")
            body = json.loads(conn.getresponse().read())
            conn.close()
            return body
        except (OSError, ValueError):
            return None

    @classmethod
    def tearDownClass(cls):
        # The extension detaches the shim it starts; stop it by the pid it reports.
        if cls.spawned_port:
            body = cls._health(cls.spawned_port)
            if body and body.get("shim") == "elm-pi":
                try:
                    os.kill(body["pid"], 15)
                except OSError:
                    pass
        for stub in cls.stubs:
            stub.shutdown()
            stub.server_close()
        if getattr(cls, "upstream", None):
            cls.upstream.stop()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def provider(self, scenario):
        providers = self.out[scenario]["providers"]
        self.assertEqual(1, len(providers), self.out[scenario])
        return providers[0]

    def test_registers_elm_shim_provider_id(self):
        self.assertEqual("elm-shim", self.provider("healthy")["id"])

    def test_base_url_is_loopback_on_configured_port(self):
        self.assertEqual(f"http://127.0.0.1:{self.ports['healthy']}", self.provider("healthy")["config"]["baseUrl"])

    def test_api_key_is_left_to_pi_to_expand(self):
        # A reference, never the key itself: the extension must not read the secret.
        self.assertEqual("$ELM_API_KEY", self.provider("healthy")["config"]["apiKey"])

    def test_speaks_openai_completions(self):
        self.assertEqual("openai-completions", self.provider("healthy")["config"]["api"])

    def test_one_model_with_id_from_environment(self):
        self.assertEqual([LLAMA], [m["id"] for m in self.provider("healthy")["config"]["models"]])

    def test_model_id_falls_back_to_template_token(self):
        # bootstrap.sh substitutes the token when it installs the extension.
        self.assertEqual("@LLAMA_MODEL@", self.provider("template")["config"]["models"][0]["id"])

    def test_max_tokens_fit_inside_the_idle_timeout(self):
        # 8192 tokens at Llama's slow end (30 tok/s) is ~273 s, under pi's 300 s idle timeout.
        self.assertLessEqual(self.provider("healthy")["config"]["models"][0]["maxTokens"] / 30, 300)

    def test_healthy_shim_needs_no_warning(self):
        self.assertEqual(([], []), (self.out["healthy"]["notes"], self.out["healthy"]["events"]))

    def test_foreign_listener_is_left_alone(self):
        self.assertEqual([], self.out["foreign"]["providers"])
        self.assertIsNotNone(self._health(self.ports["foreign"]))

    def test_foreign_listener_warns_with_path_and_port(self):
        notes = self.out["foreign"]["notes"]
        self.assertEqual([{"message": f"elm-shim: could not start {self.dir}/no-such/shim.py on "
                                      f":{self.ports['foreign']} - Llama sub-agents unavailable",
                           "level": "warn"}], notes)

    def test_failing_health_is_not_our_shim(self):
        self.assertEqual(([], ["session_start"]), (self.out["failing"]["providers"], self.out["failing"]["events"]))

    def test_missing_shim_file_gives_no_provider(self):
        self.assertEqual(([], 1), (self.out["absent"]["providers"], len(self.out["absent"]["notes"])))

    def test_default_shim_path_is_beside_agent_dir(self):
        self.assertIn("could not start /nowhere/shim/shim.py on", self.out["agentdir"]["notes"][0]["message"])

    def test_starts_the_shim_and_registers(self):
        self.assertEqual("elm-shim", self.provider("spawn")["id"])
        self.assertIsNotNone(self.spawned)

    def test_started_shim_gets_port_and_inherits_upstream(self):
        self.assertEqual((self.spawned_port, f"http://127.0.0.1:{self.upstream.port}/api/v1"),
                         (self.spawned["port"], self.spawned["upstream"]))


if __name__ == "__main__":
    unittest.main()
