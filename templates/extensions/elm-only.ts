/**
 * elm-only: restrict this pi install to the university's self-hosted models.
 *
 * Why: staff are funded at industry token rates, which does not buy a meaningful
 * amount of commercial-model usage. ELM's university-hosted models are metered
 * against the department's allocation instead, so they are the models this
 * install is for. Leaving 1,300+ commercial models one `/model` keypress away
 * invites accidental spend and support questions this team cannot answer.
 *
 * What it does: pi ships ~40 built-in providers (anthropic, openai, google,
 * bedrock, openrouter, ...). Registering a provider with an empty `models` array
 * REPLACES its catalogue, so this strips every non-allowed provider down to zero
 * models. `/model`, Ctrl+P cycling and sub-agent model selection then have
 * nothing but ELM to offer, and `/login` becomes pointless: credentials with no
 * catalogue entry are unreachable.
 *
 * What it is NOT: a security control. It shapes what this install offers; it
 * cannot stop someone installing their own agent. See LOCKDOWN.md.
 *
 * Escape hatch (documented, deliberate):
 *     PI_ELM_ALLOWED_PROVIDERS="elm,elm-shim,anthropic" pi
 * The launcher refuses to pass this through unless PI_ELM_UNLOCK=1 is also set.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const ALLOWED = new Set(
  (process.env.PI_ELM_ALLOWED_PROVIDERS ?? "elm,elm-shim")
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean),
);

const POLICY =
  "This install runs on the University's self-hosted models via the ELM gateway. " +
  "Commercial providers (Anthropic, OpenAI, Google, ...) are not available here: " +
  "staff allocations are funded at industry token rates and do not stretch to them. " +
  "See LOCKDOWN.md in the install directory for the rationale and how to raise it.";

/**
 * pi's built-in provider ids, as of 0.85.1. Stripped at load time so paths that
 * never open a session (`--list-models`) are covered too. Regenerate with the
 * probe in LOCKDOWN.md if a pi upgrade adds providers; anything missed here is
 * still caught by the dynamic pass below.
 */
const BUILTIN_PROVIDERS = [
  "amazon-bedrock", "ant-ling", "anthropic", "azure-openai-responses", "baseten",
  "cerebras", "cloudflare-ai-gateway", "cloudflare-workers-ai", "deepseek",
  "fireworks", "github-copilot", "google", "google-vertex", "groq", "huggingface",
  "kimi-coding", "minimax", "minimax-cn", "mistral", "moonshotai", "moonshotai-cn",
  "nvidia", "openai", "openai-codex", "opencode", "opencode-go", "openrouter",
  "qwen-token-plan", "qwen-token-plan-cn", "qwen-token-plan-individual", "radius", "together",
  "vercel-ai-gateway", "xai", "xiaomi", "xiaomi-token-plan-ams",
  "xiaomi-token-plan-cn", "xiaomi-token-plan-sgp", "zai", "zai-coding-cn",
];

export default function (pi: ExtensionAPI) {
  const stripped = new Set<string>();

  const nuke = (provider: string) => {
    if (ALLOWED.has(provider)) return;
    try {
      // An empty models array REPLACES the provider's catalogue with nothing.
      pi.registerProvider(provider, { models: [] });
      stripped.add(provider);
    } catch {
      // A provider that refuses composition keeps its models; the launcher's
      // credential scrub is what stops it being usable. Not fatal.
    }
  };

  // Load-time pass: covers --list-models and anything that reads the catalogue
  // before a session exists.
  for (const provider of BUILTIN_PROVIDERS) nuke(provider);

  // Session-start pass: catches providers registered by other extensions or by
  // a pi upgrade that BUILTIN_PROVIDERS does not know about.
  pi.on("session_start", async (_event, ctx: any) => {
    for (const provider of new Set<string>(
      ctx.modelRegistry.getAll().map((m: any) => m.provider as string),
    )) {
      nuke(provider);
    }
  });

  // Belt and braces: if a model outside the allowlist ever becomes current
  // (a saved session, an --api-key run, a provider registered after startup),
  // say so loudly rather than quietly billing someone.
  pi.on("model_select", async (event, ctx: any) => {
    if (ALLOWED.has(event.model.provider)) return;
    ctx.ui?.notify?.(
      `${event.model.provider}/${event.model.id} is outside this install's ELM-only policy.`,
      "error",
    );
  });

  pi.registerCommand("elm-policy", {
    description: "Why only ELM models are available here",
    handler: async (_args, ctx: any) => {
      const lines = [
        POLICY,
        "",
        `Allowed providers: ${[...ALLOWED].join(", ")}`,
        stripped.size
          ? `Catalogues stripped this session (${stripped.size}): ${[...stripped].sort().join(", ")}`
          : "No provider catalogues were stripped this session.",
      ];
      ctx.ui?.notify?.(lines.join("\n"), "info");
    },
  });
}
