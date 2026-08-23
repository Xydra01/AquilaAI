# Qwen native thinking (Ollama /api/chat)

Aquila uses Ollama’s **native** [`/api/chat`](https://docs.ollama.com/api/chat) endpoint. Thinking-capable models (Qwen 3.x, DeepSeek R1, etc.) emit reasoning in `message.thinking` separately from `message.content`.

## How it works

| Channel | Field | Used for |
|---------|-------|----------|
| Native thinking | `message.thinking` | Full chain-of-thought — GUI collapsible block, optional JSONL `thinking_trace` |
| Schema reasoning | JSON `reasoning` in `content` | Act loop memory, ledger, coach (brief operational summary) |

Structured tool turns use native `format: <json_schema>`. Only **`content`** is parsed as JSON; thinking never goes through `parse_agent_response`. On act loops, native thinking is disabled on the JSON pass to avoid parse failures — use two-phase mode instead (below).

## Two-phase act loop

When `AQUILA_ACT_TWO_PHASE=1` (default), each loop tick runs **two LLM calls** before tool execution:

1. **Think pass** (`surface=reflect`): `format=None`, native `think:true`, full reasoning budget (`AQUILA_CHAT_NUM_PREDICT_THINK`). No tool schema. Does **not** consume an episode.
2. **Act pass** (`surface=act`): strict tool JSON schema, `think:false`. Parses `tools` and executes them.

Think summaries are stored in conversation history; the act pass receives an **ACT TURN** nudge to output JSON only. Act parse retries skip the think pass (history already has the plan).

Research/task GUI pages stream thinking tokens into the agent rail when two-phase is enabled.

## Environment

| Variable | Default | Role |
|----------|---------|------|
| `AQUILA_ENABLE_THINK` | `1` | Master switch (`0` → `think: false` everywhere) |
| `AQUILA_THINK_SURFACES` | `chat,character,learn,act,explore,plan,reflect` | Comma list of surfaces that may use thinking |
| `AQUILA_ACT_TWO_PHASE` | `1` | Think pass then tool JSON act pass per loop tick (`0` to disable) |
| `AQUILA_ACT_STRUCTURED_NO_PLAIN` | `1` | Act turns: strict → shrink → `json_object` only (no plain heal) |
| `AQUILA_THINK_LEGACY_XML` | `1` | Strip think-tag XML leaked into streamed **content** only |
| `AQUILA_SKIP_WARMUP` | `0` | `1` in unit tests (mocks) |
| `AQUILA_WARMUP_REQUIRED` | `1` | Fail `chat()` if warmup cannot load model |
| `AQUILA_ACT_NUM_PREDICT` | _(unset)_ | Optional higher `num_predict` for structured act turns |
| `AQUILA_CHAT_NUM_PREDICT_THINK` | `4096` | `num_predict` when `think: true` on chat (thinking + answer share this budget) |
| `AQUILA_REPEAT_PENALTY` | `1.15` | Ollama `repeat_penalty` for plain chat (`1.0` = off) |
| `AQUILA_TQ_REPEAT_PENALTY` | `1.2` | Higher penalty when model name contains `tq` / `turboquant` |
| `AQUILA_REPEAT_LAST_N` | `64` | Ollama `repeat_last_n` window |
| `AQUILA_STREAM_MIN_CHECK_CHARS` | `200` | Start checking for repetition loops after this many content chars |

## Warmup

Every `OllamaClient.chat()` calls `ensure_warmup()` unless `AQUILA_SKIP_WARMUP=1`. Warmup uses a minimal `/api/chat` request (`think: false`, `num_predict: 8`), with `/api/generate` fallback.

Live tests use the session `ollama_warmed` fixture in `agent/tests/conftest.py`.

## Troubleshooting

| Symptom | Action |
|---------|--------|
| HTTP 400 `does not support thinking` | Model is not Qwen/thinking-capable (e.g. `aquila_NSFW` / Llama Hermes). Aquila disables `think` for those tags automatically; or set `AQUILA_ENABLE_THINK=0` |
| Learn archive hangs / 300s | Set `AQUILA_LEARN_ARCHIVE_GENERATION_CAP=0`; try `AQUILA_ENABLE_THINK=0` for archive-only |
| JSON parse errors on act loop | Enable `AQUILA_ACT_TWO_PHASE=1` for think-then-act; or rely on automatic act retry with `think: false`; check `Agent-Logs` for `format_mode_used` |
| No thinking in UI | Confirm model name contains `qwen` (or other supported family) and surface is in `AQUILA_THINK_SURFACES` |
| Cold start timeouts | Increase `AQUILA_READ_TIMEOUT_MAX`; run GUI warmup or wait for `ensure_warmup` |
| CPU-only hosts | `apply_cpu_friendly_settings()` sets `AQUILA_ENABLE_THINK=0` and `AQUILA_ACT_TWO_PHASE=0` automatically |
| Repetitive answer tail (TQ 32k) | Lower `AQUILA_CHAT_NUM_PREDICT_THINK` (e.g. `2048`); raise `AQUILA_TQ_REPEAT_PENALTY` (try `1.35`); lower `AQUILA_STREAM_MIN_CHECK_CHARS` (default `200`) |
| Thinking not visible | Pane auto-expands while thinking streams; collapses when answer starts. If TQ sends reasoning only in `content`, Aquila splits `think` tags into the pane (labeled “content stream”) |
| Thinking not collapsible | Click **▸ Thinking** above chat to re-open after the answer starts |

## Live tests

```bash
cd agent
python -m pytest tests/test_thinking_live.py -m live -q
python -m pytest tests/test_ollama_client.py tests/test_think_policy.py tests/test_loop_two_phase.py -q
```

Qwopus Coder setup: [ollama-qwopus.md](ollama-qwopus.md).
