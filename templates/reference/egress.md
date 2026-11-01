# A 403 from every host is this install, not the internet

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
