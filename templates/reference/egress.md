# A 403: this install, or the site?

**First: was this session started with `pi --remote`?** Your system prompt says
so when it was ("This session was started with `pi --remote`"), and
`echo $PI_ELM_REMOTE` prints `1`. In such a session the proxy refuses nothing -
it records each destination as `OPEN` in the egress log - so every 403, 400 or
error page is the site's own answer. Read what it says (the body, not the status
line) and do what it asks. test12 (2026-11-13), a `--remote` session, read
Wikimedia's own 403s as this proxy, told the user "the session doesn't have
`--remote`", and drew placeholder pictures instead.

Wikimedia's refusals, seen 2026-11-13:

- **403 "Please set a user-agent and respect our robot policy"**: Python's
  `urllib` (and other libraries' defaults) get this. Send a `User-Agent` that
  names the program and its use, e.g. `elm-pi-research/1.0 (University of
  Edinburgh)`; `curl`'s default passes.
- **400 "Use thumbnail sizes listed on https://w.wiki/GHai"**: a thumbnail at a
  size Commons does not serve (`/thumb/.../640px-...`), saved by `curl -o` as an
  HTML page named `.jpg`. Ask for the file by name instead -
  `https://commons.wikimedia.org/wiki/Special:FilePath/<File name>?width=960` -
  or take the original's `upload.wikimedia.org` URL from its file page.
- **404 from `Special:FilePath`**: no file has that name. test13 guessed
  `African_Elephant_Botswana_2015.jpg`. Take names from Commons' search instead:
  `https://commons.wikimedia.org/w/api.php?action=query&list=search&srnamespace=6&srsearch=African+elephant&format=json`
  lists `File:` titles (`File:African Bush Elephant.jpg`), each one that works.
- **429 Too Many Requests** from `upload.wikimedia.org`: too many requests at
  once. test14 had five page agents, then the parent, all downloading - most of
  them guessed names - and every request after that got 429, with or without a
  `User-Agent`. Fetch every picture in one place, yourself or one agent, before
  the agents that write pages start: names from the search, one after another.
  (Not the ELM gateway's `429 rate_limit_exceeded`, below.)

The rest of this page is about a session **without** `--remote`.

Everything pi does leaves through an allowlisting proxy on loopback. On its list
are the ELM gateway, PyPI (`pypi.org`, `files.pythonhosted.org`), conda-forge
(`conda.anaconda.org`, `api.anaconda.org`, `prefix.dev`) and the container
registries (Docker Hub, GHCR, Quay) - see `proxyAllow` in the install's
`config/elm-pi.json`. A host that is not on it gets **403 Forbidden**, which
looks exactly like a site refusing you.

Measured here, the cost of not knowing that: a session downloading images read
403s from `atlas.cern`, `home.cern`, `upload.wikimedia.org`, `images.nasa.gov`
and `www.ed.ac.uk`, concluded "all the major science institutions block
hotlinking", and spent 6.2M tokens across two workflows working around a
restriction that did not exist. The tell was in the same output: `picsum.photos`,
`via.placeholder.com` and `placekitten.com` returned 403 too, and those exist to
be hotlinked. **When every host fails the same way, suspect the near end.**

Two things identify it in one call each:

```bash
curl -sI https://example.com | grep -i x-elm-pi    # X-Elm-Pi-Egress: refused
tail -5 "$PI_CODING_AGENT_DIR/egress.log"          # REJECTED <host> not on the allowlist
```

The refusal carries `X-Elm-Pi-Egress`, `X-Elm-Pi-Reason` and `X-Elm-Pi-Remedy`
headers, and the body says so in full - but `curl -I` shows only headers, `curl
-o` writes the body into the file and `curl -s` discards it, so check the
headers or the log rather than the status line alone.

**The remedy is the session, not the URL.** Reaching anything outside the list
needs `pi --remote`, which puts the proxy in open mode - it then records each
destination instead of refusing it. A session already running cannot be
upgraded: nothing in it will reach the web, so say that plainly rather than
hunting for a host that works. Switching to a different image source is not a
fix, and neither is a placeholder service.

Under `pi --remote` both `https://` and `http://` work. Outside it, both fail,
and the egress log names every host that tried.

A `429 rate_limit_exceeded` is different: it comes from the ELM gateway itself
(a limit on the shared model), and pi retries it on its own.
