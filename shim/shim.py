#!/usr/bin/env python3
"""
ELM tool-call shim.

ELM's vLLM instances for Llama 3.3 and EuroLLM were started without
--enable-auto-tool-choice / --tool-call-parser, so any request carrying `tools`
fails with HTTP 400. This service sits in front of ELM and gives those models
OpenAI-compatible tool calling by prompt engineering:

  request  : lift `tools` into a system block, strip tools/tool_choice,
             rewrite prior tool_calls / tool-results into plain text
  response : parse a JSON function call out of the text and re-emit it as
             OpenAI `tool_calls` with finish_reason="tool_calls"

Models that already support tools natively (Qwen, the OpenAI ones) are passed
through untouched.
"""
import glob, http.server, json, os, re, socket, socketserver, ssl, sys, threading, time, urllib.error, urllib.request, uuid

UPSTREAM = os.environ.get("ELM_BASE_URL", "https://elm.edina.ac.uk/api/v1")
PORT     = int(os.environ.get("SHIM_PORT", "8811"))
CAFILE   = os.environ.get("SHIM_CAFILE", "/etc/ssl/cert.pem")
# models that need the shim; everything else passes straight through
SHIM_MODELS = tuple(filter(None, os.environ.get(
    "SHIM_MODELS",
    "meta-llama/Llama-3.3-70B-Instruct,utter-project/EuroLLM-22B-Instruct-2512").split(",")))
CTX = ssl.create_default_context(cafile=CAFILE) if os.path.exists(CAFILE) else ssl.create_default_context()
# Answered locally, never forwarded: elm-shim.ts uses it to tell this shim from
# whatever else might be listening on the port.
HEALTH_PATH = "/__elm_shim__/health"


# --- the egress proxy, resolved per request ---------------------------------
# This shim outlives the pi session that starts it: elm-shim.ts reuses one that
# is already listening, so a fan-out of sub-agent children does not start dozens
# of copies. The launcher's egress proxy does *not* outlive its session - it
# binds an ephemeral port and dies with the shell. A shim that kept the proxy
# address it was handed in its environment therefore went on dialling a port
# that had gone, every Llama request failed with "Connection refused", and
# pi-subagents recorded that as a model exclusion and stopped using Llama.
#
# So the proxy is resolved when it is needed rather than once at startup: the
# address from the environment first, then the newest port file any live
# elm-pi session has left behind. The answer is cached until it stops answering.
PROXY_GLOB = os.path.join(os.environ.get("TMPDIR", "/tmp"), "elm-pi-egress-*.port")
# Whether this shim is expected to go through a proxy at all. Decided once, from
# the environment the launcher gave it: a shim started by hand outside elm-pi
# has no proxy to find and should talk to ELM directly rather than fail.
PROXY_MANAGED = bool(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"))
_proxy_lock = threading.Lock()
_proxy_cached = None


def _accepting(url):
    """True if something is listening where this proxy URL points."""
    try:
        hostport = url.split("://", 1)[-1].rstrip("/").rsplit("@", 1)[-1]
        host, _, port = hostport.rpartition(":")
        with socket.create_connection((host or "127.0.0.1", int(port)), 0.4):
            return True
    except (OSError, ValueError):
        return False


def _proxy_candidates():
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        value = os.environ.get(key)
        if value:
            yield value
    # Newest first: the most recently started session is the one most likely to
    # still be running.
    try:
        files = sorted(glob.glob(PROXY_GLOB), key=os.path.getmtime, reverse=True)
    except OSError:
        files = []
    for path in files:
        try:
            yield "http://127.0.0.1:%d" % int(open(path).read().strip())
        except (OSError, ValueError):
            continue


def resolve_proxy(force=False):
    """The proxy to use now, or None if there is no live one to use."""
    global _proxy_cached
    with _proxy_lock:
        if not force and _proxy_cached and _accepting(_proxy_cached):
            return _proxy_cached
        seen = set()
        for url in _proxy_candidates():
            if url in seen:
                continue
            seen.add(url)
            if _accepting(url):
                _proxy_cached = url
                return url
        _proxy_cached = None
        return None


def _build_opener():
    proxy = resolve_proxy() if PROXY_MANAGED else None
    if PROXY_MANAGED and not proxy:
        # Fail loudly rather than reaching ELM directly: this install routes
        # everything through an allowlisting proxy on purpose.
        raise RuntimeError(
            "no live elm-pi egress proxy - the session that started this shim "
            "has exited. Start pi again; the shim will pick up its proxy."
        )
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=CTX),
        urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else {}),
    )


def _url(path):
    """Join UPSTREAM and a client path without duplicating the version segment.

    OpenAI clients (pi included) append /v1/chat/completions to the base URL they
    are given. ELM_BASE_URL already ends in /api/v1, so a naive concatenation
    produced .../api/v1/v1/chat/completions and the gateway answered
    400 "Unknown or unsupported endpoint". Only requests carrying `tools` were
    exercised before, and those take the shimmed branch which builds its own
    path, so the passthrough branch was broken without anyone noticing.
    """
    base = UPSTREAM.rstrip("/")
    if base.endswith("/v1") and (path == "/v1" or path.startswith("/v1/")):
        path = path[len("/v1"):] or "/"
    return base + path


INSTRUCTIONS = """You can call functions. The available functions are listed below, one JSON schema per line:

{tools}

To call a function, reply with ONLY a single-line JSON object and nothing else:
{{"name": "<function name>", "arguments": {{...}}}}

Rules:
- Emit the JSON alone. No prose before or after it, no markdown fence.
- Call a function only when it is actually needed to answer.
- If no function is needed, reply normally in plain prose.
- Function results come back as messages beginning "FUNCTION RESULT".
- After a FUNCTION RESULT, decide: is the user's task now COMPLETE?
  - NOT complete -> emit the next function call as JSON immediately. Do NOT describe
    what you would do, would need to do, or are about to do. Narrating an action
    instead of calling the function is a failure: the action never happens.
  - Complete -> give the final answer in plain prose.
- Never say "I would need to", "to do this you would", or "the next step is" in place
  of a call. If an action is needed, emit the JSON call for it now."""


def tools_to_prompt(tools):
    lines = []
    for t in tools:
        fn = t.get("function", t) or {}
        lines.append(json.dumps({
            "name": fn.get("name"),
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {}),
        }, separators=(",", ":")))
    return INSTRUCTIONS.format(tools="\n".join(lines))


def flatten_messages(messages):
    """Rewrite assistant tool_calls and tool-result messages into plain text."""
    out = []
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                fn = c.get("function", {})
                args = fn.get("arguments")
                if isinstance(args, str):
                    try: args = json.loads(args)
                    except Exception: pass
                calls.append(json.dumps({"name": fn.get("name"), "arguments": args},
                                        separators=(",", ":")))
            text = (m.get("content") or "") + ("\n" if m.get("content") else "") + "\n".join(calls)
            out.append({"role": "assistant", "content": text.strip()})
        elif role == "tool":
            name = m.get("name") or "function"
            out.append({"role": "user",
                        "content": (f"FUNCTION RESULT ({name}):\n{m.get('content','')}\n\n"
                                    "If the task is not finished, emit the next function call "
                                    "as a single-line JSON object NOW. Do not describe the action "
                                    "- perform it. If the task is finished, give the final answer.")})
        else:
            mm = {k: v for k, v in m.items() if k not in ("tool_calls", "tool_call_id", "name")}
            out.append(mm)
    return out


_JSON_CALL = re.compile(r'\{.*?"name"\s*:\s*".+?".*?\}\s*$', re.S)

def extract_call(text, valid_names):
    """Return (tool_calls, leftover_text) parsed out of the model's prose."""
    if not text:
        return None, text
    s = text.strip()
    s = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", s).strip()   # strip any fence
    candidates = []
    if s.startswith("{"):
        candidates.append(s)
    m = _JSON_CALL.search(s)
    if m:
        candidates.append(m.group(0))
    # Scan for ANY balanced {...} span containing "name" - Llama often wraps the
    # call in prose ("Let me read it: {...} now."), which earlier versions missed.
    for start in [i for i, ch in enumerate(s) if ch == "{"]:
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{": depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    span = s[start:i + 1]
                    if '"name"' in span:
                        candidates.append(span)
                    break
        if len(candidates) > 4:
            break
    # Also try the first balanced {...} span, for calls with trailing prose.
    if s.startswith("{"):
        depth = 0
        for i, ch in enumerate(s):
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(s[:i + 1]); break
    for cand in candidates:
        obj = None
        # strict=False tolerates the literal newlines Llama emits inside JSON
        # strings instead of \n escapes - the single most common failure here.
        for strict in (False,):
            try:
                obj = json.loads(cand, strict=strict); break
            except Exception:
                pass
        if obj is None:
            continue
        name = obj.get("name")
        if not name or (valid_names and name not in valid_names):
            continue
        args = obj.get("arguments", obj.get("parameters", {}))
        if not isinstance(args, str):
            args = json.dumps(args)
        return [{
            "id": "call_" + uuid.uuid4().hex[:16],
            "type": "function",
            "function": {"name": name, "arguments": args},
        }], ""
    return None, text


def sse(obj):
    return b"data: " + json.dumps(obj).encode() + b"\n\n"


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass

    def _send(self, code, payload, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _upstream(self, path, body, headers, stream=False):
        req = urllib.request.Request(_url(path), data=body, method="POST" if body else "GET")
        for k, v in headers.items():
            if k.lower() not in ("host", "content-length", "accept-encoding", "connection"):
                req.add_header(k, v)
        try:
            return _build_opener().open(req, timeout=900)
        except urllib.error.URLError as err:
            # A proxy that was answering when we resolved it can go away between
            # one request and the next - the session owning it exits. Re-resolve
            # once and try again before reporting a failure, because the caller
            # turns a failure here into a 24-hour model exclusion.
            if not PROXY_MANAGED or not isinstance(err.reason, OSError):
                raise
            resolve_proxy(force=True)
            return _build_opener().open(req, timeout=900)

    def do_GET(self):
        if self.path.split("?", 1)[0] == HEALTH_PATH:
            proxy = resolve_proxy() if PROXY_MANAGED else None
            self._send(200, json.dumps({
                "shim": "elm-pi",
                "pid": os.getpid(),
                "port": PORT,
                "upstream": UPSTREAM,
                "proxyManaged": PROXY_MANAGED,
                "proxy": proxy,
                "proxyFromEnv": os.environ.get("HTTPS_PROXY", ""),
                "models": list(SHIM_MODELS),
            }).encode())
            return
        try:
            with self._upstream(self.path, None, self.headers) as r:
                self._send(r.status, r.read(), r.headers.get("Content-Type", "application/json"))
        except urllib.error.HTTPError as e:
            self._send(e.code, e.read())
        except Exception as e:
            self._send(502, json.dumps({"error": {"message": str(e)}}).encode())

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            payload = {}

        model = payload.get("model", "")
        tools = payload.get("tools")
        needs_shim = ("chat/completions" in self.path and tools and
                      any(model == m or model.startswith(m) for m in SHIM_MODELS))

        if not needs_shim:                      # transparent passthrough
            try:
                with self._upstream(self.path, raw, self.headers) as r:
                    if payload.get("stream"):
                        self.send_response(r.status)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Transfer-Encoding", "chunked")
                        self.end_headers()
                        while True:
                            c = r.read(2048)
                            if not c: break
                            self.wfile.write(b"%X\r\n" % len(c)); self.wfile.write(c)
                            self.wfile.write(b"\r\n"); self.wfile.flush()
                        self.wfile.write(b"0\r\n\r\n"); self.wfile.flush()
                    else:
                        self._send(r.status, r.read(), r.headers.get("Content-Type", "application/json"))
            except urllib.error.HTTPError as e:
                self._send(e.code, e.read())
            except Exception as e:
                self._send(502, json.dumps({"error": {"message": str(e)}}).encode())
            return

        # ---- shimmed path -------------------------------------------------
        valid = {(t.get("function", t) or {}).get("name") for t in tools}
        msgs = flatten_messages(payload.get("messages", []))
        sys_block = tools_to_prompt(tools)
        if msgs and msgs[0].get("role") in ("system", "developer"):
            msgs[0] = {"role": "system",
                       "content": (msgs[0].get("content") or "") + "\n\n" + sys_block}
        else:
            msgs.insert(0, {"role": "system", "content": sys_block})

        want_stream = bool(payload.get("stream"))
        up = {k: v for k, v in payload.items()
              if k not in ("tools", "tool_choice", "stream", "stream_options", "parallel_tool_calls")}
        up["messages"] = msgs
        up["stream"] = False                      # always buffer upstream, re-emit below
        # Emitting a well-formed call is a parsing task, not a creative one. Measured
        # on Llama 3.3: at default temperature the two-step read->replace loop
        # completed ~50% of the time; at temperature 0 it was 6/6.
        up["temperature"] = float(os.environ.get("SHIM_TEMPERATURE", "0"))

        try:
            with self._upstream("/chat/completions", json.dumps(up).encode(), self.headers) as r:
                result = json.loads(r.read())
        except urllib.error.HTTPError as e:
            self._send(e.code, e.read()); return
        except Exception as e:
            self._send(502, json.dumps({"error": {"message": str(e)}}).encode()); return

        if "error" in result:
            self._send(400, json.dumps(result).encode()); return

        choice = (result.get("choices") or [{}])[0]
        msg = choice.get("message", {}) or {}
        calls, leftover = extract_call(msg.get("content") or "", valid)
        if calls:
            msg = {"role": "assistant", "content": None, "tool_calls": calls}
            choice["finish_reason"] = "tool_calls"
        else:
            msg = {"role": "assistant", "content": leftover}
            choice.setdefault("finish_reason", "stop")
        choice["message"] = msg
        result["choices"] = [choice]

        if not want_stream:
            self._send(200, json.dumps(result).encode()); return

        # re-emit as a single-shot SSE stream so streaming clients work
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        cid = result.get("id", "chatcmpl-shim"); created = result.get("created", int(time.time()))
        base = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model}
        def emit(delta, finish=None):
            chunk = dict(base); chunk["choices"] = [{"index": 0, "delta": delta, "finish_reason": finish}]
            b = sse(chunk)
            self.wfile.write(b"%X\r\n" % len(b)); self.wfile.write(b); self.wfile.write(b"\r\n"); self.wfile.flush()
        emit({"role": "assistant", "content": ""})
        if calls:
            emit({"tool_calls": [{"index": 0, "id": calls[0]["id"], "type": "function",
                                  "function": calls[0]["function"]}]})
            emit({}, "tool_calls")
        else:
            emit({"content": msg.get("content") or ""})
            emit({}, "stop")
        done = dict(base); done["choices"] = [{"index": 0, "delta": {}, "finish_reason": None}]
        done["usage"] = result.get("usage")
        b = sse(done) + b"data: [DONE]\n\n"
        self.wfile.write(b"%X\r\n" % len(b)); self.wfile.write(b); self.wfile.write(b"\r\n")
        self.wfile.write(b"0\r\n\r\n"); self.wfile.flush()


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    print(f"elm-tool-shim on 127.0.0.1:{PORT} -> {UPSTREAM}", file=sys.stderr)
    print(f"  shimming: {', '.join(SHIM_MODELS)}", file=sys.stderr)
    Server(("127.0.0.1", PORT), Handler).serve_forever()
