# Sources behind the model settings

Gathered 2026-11-11. Each line says where a claim comes from, quoted where the
wording matters, and how strong it is. What was measured on ELM itself is in
[README.md](README.md) and the files beside it, not here.

## Mistral Small 4 (`mistralai/Mistral-Small-4-119B-2603`)

- **Architecture.** "MoE: 128 experts, 4 active", "119B parameters, with 6.5B
  activated per token", 256k context, text and image input.
  https://huggingface.co/mistralai/Mistral-Small-4-119B-2603 (model card).
  Mistral's blog gives "6B active parameters per token (8B including embedding
  and output layers)". https://mistral.ai/news/mistral-small-4
- **Sampling.** "Temperature: 0.7 for `reasoning_effort="high"`. Temp between
  0.0 and 0.7 for `reasoning_effort="none"` depending on task." The card's tool
  example uses 0.1. A Mistral engineer: "0.1 is the temperature we recommend for
  an Instruct checkpoint".
  https://huggingface.co/mistralai/Mistral-Small-4-119B-2603/discussions/4
- **No sampling defaults ship with it.** `generation_config.json` has bos/eos/pad
  and `max_length` only.
  https://huggingface.co/mistralai/Mistral-Small-4-119B-2603/blob/main/generation_config.json
  With nothing there, vLLM falls back to temperature 1.0, top_p 1.0
  (`_DEFAULT_SAMPLING_PARAMS`, applied user, then server default, then OpenAI
  default).
  https://github.com/vllm-project/vllm/blob/main/vllm/entrypoints/openai/chat_completion/protocol.py
  Confirmed on ELM by the temperature probe (`2026-11-11/temperature-probe.json`).
- **Reasoning switch.** `reasoning_effort` "none" (the template's default) or
  "high"; the template rejects other values.
  https://huggingface.co/mistralai/Mistral-Small-4-119B-2603/blob/main/chat_template.jinja
- **The "claims done, did nothing" failure is known.** HF discussion #16:
  responds with "Task completed" instead of doing the task, also on Mistral's own
  API; reported to go away with `reasoning_effort` high or a forceful prompt line.
  No reply from Mistral. Anecdotal, several users.
  https://huggingface.co/mistralai/Mistral-Small-4-119B-2603/discussions/16
- **Small Mistral models answer in prose instead of acting.** AgentFloor
  (arXiv 2605.00334, May 2026): mistral-small3.2 93% on single tool calls, 16% on
  two-tool chains; ministral-3:8b "emits a final-text answer without invoking"
  the tool, fixed by "you MUST call submit_decision". A benchmark, but on older
  Mistral models. https://arxiv.org/html/2605.00334
- **Mistral's own coding agent's rules.** Vibe's prompt: "If the task requires
  an edit, edit. Do not stop at describing the change." and "Do not claim
  'verified', 'tested', 'working', or 'complete' unless a corresponding execution
  step appears in the trajectory". Vibe uses Small 4 only for compaction and
  utility calls, at temperature 0.2 with thinking off.
  https://github.com/mistralai/mistral-vibe/blob/main/vibe/core/prompts/cli.md,
  https://github.com/mistralai/mistral-vibe/blob/main/vibe/core/agents/models.py
- **Mistral's coding model is another one.** Mistral Medium 3.5 "supersedes all
  our previous coding models, namely Devstral".
  https://huggingface.co/mistralai/Mistral-Medium-3.5-128B
- **Serving.** vLLM before 0.20.0 broke Small 4's tool and reasoning parsing;
  the symptom is `[TOOL_CALLS]` in the reply text.
  https://recipes.vllm.ai/mistralai/Mistral-Small-4-119B-2603 ,
  https://github.com/vllm-project/vllm/pull/39217
  None of 1,018 Mistral replies on ELM showed it (README.md).
- **`developer` role.** "Unknown message role: developer" is mistral_common's
  own error; mistral_common 1.13.1 (2026-11-02, PR #430) maps `developer` to
  `system`.
  https://github.com/mistralai/mistral-common/blob/main/src/mistral_common/protocol/instruct/converters.py
- **Dense against mixture-of-experts.** NVIDIA cites Artificial Analysis
  Intelligence Index 20 for Small 4 against 30 for the dense Gemma 4 31B.
  https://developer.nvidia.com/blog/dense-vs-moe-models-active-parameters-throughput-and-when-to-choose-each/

## Qwen 3.5 (`Qwen/Qwen3.5-397B-A17B-FP8`)

- **Sampling.** Thinking: "temperature=0.6, top_p=0.95, top_k=20, min_p=0.0,
  presence_penalty=0.0, repetition_penalty=1.0". Instruct (non-thinking):
  "temperature=0.7, top_p=0.8, top_k=20, min_p=0.0, presence_penalty=1.5,
  repetition_penalty=1.0". On the penalty: "you can adjust the presence_penalty
  parameter between 0 and 2 to reduce endless repetitions", with a warning that a
  higher value "may occasionally result in language mixing and a slight decrease
  in model performance". No separate coding or agentic values.
  https://huggingface.co/Qwen/Qwen3.5-397B-A17B-FP8
- **Server default.** `generation_config.json`: temperature 0.6, top_k 20,
  top_p 0.95 - the thinking profile, which a client that sends nothing gets even
  with thinking off.
  https://huggingface.co/Qwen/Qwen3.5-397B-A17B-FP8/raw/main/generation_config.json
- **Output length.** "We recommend using an output length of 32,768 tokens for
  most queries", 81,920 for hard maths and programming benchmarks.

## Llama 3.3 (`meta-llama/Llama-3.3-70B-Instruct`)

- The model card states no sampling values; its `generation_config.json` is
  behind Meta's licence login and could not be read.
  https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct
  The 0.6 / top_p 0.9 in `elm-shim.ts` is, from memory and unverified here, what
  Meta's Llama 3 releases ship with. On this gateway it is whatever the shim
  sends, since the shim always sets it; the tuning runs test it directly.

## Sampling beyond temperature (top_p, top_k, min_p, penalties)

Gathered 2026-11-11 for the top_p/top_k sweep. The headline: no published study
tests top_k, top_p, min_p or the penalties on agentic coding or tool calling, for
these models or any other. What exists:

- **Qwen 3.5.** Two profiles on the card - thinking: temperature 0.6, top_p 0.95,
  top_k 20, min_p 0, presence 0; instruct: 0.7, 0.8, 20, 0, presence 1.5 - and
  presence_penalty "between 0 and 2 to reduce endless repetitions", with "a
  slight decrease in model performance" at higher values.
  https://huggingface.co/Qwen/Qwen3.5-397B-A17B . The smaller Qwen3.5/3.6 cards
  add a "precise coding tasks" profile with presence 0
  (https://huggingface.co/Qwen/Qwen3.5-35B-A3B, https://huggingface.co/Qwen/Qwen3.6-35B-A3B);
  the Qwen3 report ran its non-thinking coding evaluations with presence 1.5
  (https://arxiv.org/abs/2505.09388). Qwen3-Coder recommends repetition_penalty
  1.05 (https://huggingface.co/Qwen/Qwen3-Coder-480B-A35B-Instruct); Qwen3-Coder-Next
  temperature 1.0, top_p 0.95, top_k 40 (https://huggingface.co/Qwen/Qwen3-Coder-Next).
  Never greedy in thinking mode (https://huggingface.co/Qwen/Qwen3-235B-A22B).
- **Mistral.** Small 4's card is silent on top_p/top_k/min_p/penalties; the API
  docs: "We generally recommend altering this [temperature] or top_p but not
  both" (https://docs.mistral.ai/api). Magistral Small 2509 uses top_p 0.95
  (https://huggingface.co/mistralai/Magistral-Small-2509).
- **Llama 3.3.** Meta's defaults are temperature 0.6, top_p 0.9
  (https://github.com/meta-llama/llama-models/blob/main/models/llama3/generation.py).
  Databricks found function-calling accuracy varied by up to 10 points between
  temperature 0 and 0.7, with 0 usually best
  (https://www.databricks.com/blog/unpacking-function-calling-eval, benchmark).
- **Agentic runs.** SWE-bench with Qwen3-32B, 10 runs a setting: temperature 0.6
  vs 0 not significantly different; run-to-run spread 0.7-1.8 points even at 0
  (https://arxiv.org/abs/2602.07150, preprint).
- **General.** Temperature 0-1 had no significant effect on single-turn problem
  solving (https://arxiv.org/abs/2402.05201); greedy beat sampling on most
  benchmarks, code most sensitive (https://arxiv.org/abs/2407.10457); min_p's
  advantage did not survive controlling for tuning effort
  (https://arxiv.org/abs/2506.13681 against https://arxiv.org/abs/2407.01082).
- **vLLM.** Penalties are applied first, then temperature, then min_p, then
  top_k/top_p; top_k 0 or -1 and top_p 1.0 and min_p 0 mean off; presence and
  frequency penalties count only generated tokens, repetition_penalty the prompt
  too (https://docs.vllm.ai/en/latest/api/vllm/sampling_params/). At temperature
  0.7, presence 1.5 multiplies a used token's probability by about 0.12 (our
  arithmetic) - including the brackets, quotes and keys code and tool calls
  repeat. Penalties breaking JSON rests on mechanism and anecdote only.
- **How many runs.** Detecting a 3-5 point difference needs roughly 300-500
  paired task runs per comparison (McNemar, power 0.8; https://arxiv.org/abs/2411.00640
  on clustering by task) - which is why every sweep here carries an A/A control.
- **Measured here.** What ELM itself showed for these settings, 2026-11-12, is in
  [README.md](README.md), "top_p, top_k, min_p and the presence penalty": no
  change for any of the three. Mistral's top_p 0.8, which looked 6 points better
  once, came out +1.4 (p 0.63) when tested again on its own.
