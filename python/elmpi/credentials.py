"""Layer 1 of the ELM-only policy: the credentials a paid provider would need.

Only LLM-provider credentials are removed, and only from pi's own environment -
the researcher's shell is untouched. AWS_* and GITHUB_* are deliberately left
alone: the agent's bash tool needs them for real work, and the catalogue strip
(agent/extensions/elm-only.ts) already removes bedrock and copilot from the
providers pi can see.

The list is `providerCredentials` in config/elm-pi.json, written into
agent/runtime.env by scripts/elm_config.py. tests/test_install_fixes.py
checks it against every key the installed pi-ai reads.
"""


def scrub(env):
    """Remove every provider credential, and any allowlist the caller added.

    PI_ELM_ALLOWED_PROVIDERS is unset as well because the argument guard reads
    it: leaving it in the environment would let `PI_ELM_ALLOWED_PROVIDERS=...`
    in a shell widen the model policy for every session started from there.
    """
    for name in env.get("ELM_PROVIDER_CREDENTIALS").split():
        env.unset(name)
    env.unset("PI_ELM_ALLOWED_PROVIDERS")
