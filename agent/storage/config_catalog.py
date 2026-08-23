"""Single source of truth for Aquila user-facing settings (catalog + env example generation)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .workspace_paths import REPO_ROOT

SettingType = Literal["bool", "int", "float", "str"]

# Keys referenced in code/tests but not exposed in Settings GUI.
INTERNAL_KEYS: frozenset[str] = frozenset({
    "AQUILA_TEST_PERSIST_CHROMA",
    "AQUILA_QWOPUS_PARSE_ATTEMPTS",
    "AQUILA_HERETIC_PARSE_ATTEMPTS",
    "AQUILA_LIVE_STRUCTURED_TRIALS",
    "AQUILA_LIVE_STRUCTURED_ATTEMPTS",
    "AQUILA_LIVE_STRUCTURED_PAUSE_SEC",
    "AQUILA_LIVE_KEEP_ALIVE",
    "AQUILA_LIVE_INFRA_RETRY_SLEEP_SEC",
    "AQUILA_HARNESS_FORCE_MICRO_PLAN",
    "AQUILA_DATA_ROOT",
    "AQUILA_SKIP_MIGRATE",
    "AQUILA_BASH_BIN",
    "AQUILA_REMOTE_NO_AUTH",
    "AQUILA_STDIO_MCP_HOST",
    "AQUILA_LAUNCH_MODE",
    "AQUILA_SHOW_SETUP_WIZARD",
    "AQUILA_OLLAMA_VERSION",
    "AQUILA_DIAG_TRIALS",
    "AQUILA_DIAG_PROMPT",
    "AQUILA_DIAG_JSON_PATH",
    "AQUILA_PROBE_TIMEOUT_S",
    "FROM_EMAIL",
    "OLLAMA_FLASH_ATTENTION",
    "OLLAMA_KV_CACHE_TYPE",
})

# Managed by dedicated Settings pages (AI Engine, Web Search, Email).
STRUCTURED_UI_KEYS: frozenset[str] = frozenset({
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_NUM_CTX",
    "OLLAMA_KEEP_ALIVE",
    "SEARXNG_BASE_URL",
    "SEARXNG_ENGINES",
    "SMTP_SERVER",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_USE_TLS",
})


@dataclass(frozen=True)
class SettingDef:
    key: str
    type: SettingType
    default: str
    label: str
    description: str = ""
    tier: int = 1
    advanced: bool = False
    export_env: bool = True


@dataclass(frozen=True)
class CatalogSection:
    id: str
    title: str
    description: str
    tier: int
    settings: tuple[SettingDef, ...]


def _s(
    key: str,
    type: SettingType,
    default: str,
    label: str,
    description: str = "",
    *,
    tier: int = 1,
    advanced: bool = False,
    export_env: bool = True,
) -> SettingDef:
    return SettingDef(
        key=key,
        type=type,
        default=default,
        label=label,
        description=description,
        tier=tier,
        advanced=advanced,
        export_env=export_env,
    )


CATALOG_SECTIONS: tuple[CatalogSection, ...] = (
    CatalogSection(
        id="chat_light_research",
        title="Chat & light research",
        description=(
            "Light web research in Chat Mode. Pasted URLs in your message are fetched "
            "separately from URLs auto-scraped from SearXNG search results."
        ),
        tier=1,
        settings=(
            _s(
                "AQUILA_LIGHT_RESEARCH_MAX_USER_URLS",
                "int",
                "3",
                "Max URLs detected per message",
                "How many http(s) links to extract from a single chat message.",
            ),
            _s(
                "AQUILA_LIGHT_RESEARCH_USER_URL_READS",
                "int",
                "2",
                "Max pasted URLs to fetch",
                "How many of those links are actually downloaded and injected into context.",
            ),
            _s(
                "AQUILA_LIGHT_RESEARCH_MAX_SEARCHES",
                "int",
                "2",
                "Max web searches per message",
            ),
            _s(
                "AQUILA_LIGHT_RESEARCH_MAX_QUERY_WORDS",
                "int",
                "18",
                "Max words per search query",
            ),
            _s(
                "AQUILA_LIGHT_RESEARCH_MAX_URLS",
                "int",
                "1",
                "Auto-scrape URLs from search results",
                "Not the same as pasted user links — caps follow-up page reads from SearXNG hits.",
            ),
            _s(
                "AQUILA_LIGHT_RESEARCH_MAX_READS",
                "int",
                "1",
                "Max search-result page reads",
            ),
            _s(
                "AQUILA_LIGHT_RESEARCH_SCRAPE_CHAR_CAP",
                "int",
                "8000",
                "Scrape character cap",
            ),
            _s(
                "AQUILA_LIGHT_RESEARCH_READ_MAX_CHARS",
                "int",
                "8000",
                "User URL read character cap",
            ),
        ),
    ),
    CatalogSection(
        id="chat_light_coding",
        title="Chat & light coding",
        description="Repo snapshot injected before chat when Light coding is enabled.",
        tier=1,
        settings=(
            _s("AQUILA_LIGHT_CODING_TOKEN_BUDGET", "int", "20000", "Token budget"),
            _s("AQUILA_LIGHT_CODING_MAX_FILES_FULL", "int", "40", "Max full files"),
            _s("AQUILA_LIGHT_CODING_FILE_CHAR_CAP", "int", "12000", "Per-file character cap"),
            _s("AQUILA_LIGHT_CODING_MAX_WALK_FILES", "int", "2000", "Max walk files"),
            _s("AQUILA_LIGHT_CODING_GREP_MAX", "int", "30", "Grep result cap"),
        ),
    ),
    CatalogSection(
        id="thinking_chat",
        title="Thinking & chat",
        description="Native Qwen thinking and chat generation limits.",
        tier=1,
        settings=(
            _s("AQUILA_ENABLE_THINK", "bool", "1", "Enable native thinking"),
            _s(
                "AQUILA_THINK_SURFACES",
                "str",
                "chat,character,learn,act,explore,plan,reflect",
                "Thinking surfaces (comma list)",
            ),
            _s("AQUILA_ACT_TWO_PHASE", "bool", "1", "Two-phase act loop (think then tools)"),
            _s("AQUILA_ACT_STRUCTURED_NO_PLAIN", "bool", "1", "Act: no plain JSON fallback"),
            _s("AQUILA_THINK_LEGACY_XML", "bool", "1", "Strip legacy think XML from content"),
            _s("AQUILA_STRIP_THINK_STREAM", "bool", "1", "Strip think tags while streaming"),
            _s("AQUILA_CHAT_NUM_PREDICT", "int", "2048", "Chat max tokens (no thinking)"),
            _s("AQUILA_CHAT_NUM_PREDICT_THINK", "int", "4096", "Chat max tokens (with thinking)"),
            _s("AQUILA_COMPACT_CHAT", "bool", "0", "Compact chat system prompt (CPU)"),
            _s("AQUILA_REPEAT_PENALTY", "float", "1.15", "Repeat penalty"),
            _s("AQUILA_TQ_REPEAT_PENALTY", "float", "1.3", "TurboQuant repeat penalty"),
            _s("AQUILA_REPEAT_LAST_N", "int", "64", "Repeat penalty window"),
            _s("AQUILA_KILL_SWITCH_MODE", "str", "stall", "Generation kill switch mode"),
        ),
    ),
    CatalogSection(
        id="tasks_act_loop",
        title="Tasks & act loop",
        description="Tool loop, planning, and task execution.",
        tier=1,
        settings=(
            _s("AQUILA_ROUTE_TOOLS", "bool", "1", "Semantic tool routing"),
            _s("AQUILA_ACT_NUM_PREDICT", "int", "4096", "Act pass max tokens"),
            _s("AQUILA_ACT_JSON_PREFILL", "bool", "1", "Act JSON prefill"),
            _s("AQUILA_ACT_STREAM", "bool", "1", "Stream act pass"),
            _s("AQUILA_LEGACY_ACT_REFLECT", "bool", "0", "Legacy reflect pass"),
            _s("AQUILA_MAX_LOOP_TICKS", "int", "50", "Max loop ticks"),
            _s("AQUILA_FINAL_STEP_STALL_LIMIT", "int", "8", "Final step stall limit"),
            _s("AQUILA_STALL_HALT_TURNS", "int", "8", "Stall halt turns"),
            _s("AQUILA_LLM_ERROR_LIMIT", "int", "3", "Consecutive LLM errors before abort"),
            _s("AQUILA_FAST_PATH", "bool", "1", "Fast path micro-plans"),
            _s("AQUILA_MICRO_PLAN_MAX_WORDS", "int", "80", "Micro-plan max words"),
            _s("AQUILA_MICRO_PLAN_CODE_SINGLE", "bool", "0", "Micro-plan code single-file"),
            _s("AQUILA_EXPLORE_BRIEF", "bool", "0", "Pre-plan explore brief"),
            _s("AQUILA_PLAN_REVIEW", "bool", "1", "Plan review gate"),
            _s("AQUILA_PLAN_AUTO_APPROVE_MICRO", "bool", "0", "Auto-approve micro-plans"),
            _s("AQUILA_PLAN_NUM_PREDICT", "int", "1536", "Plan JSON token cap"),
            _s("AQUILA_PLAN_STRUCTURED_NO_PLAIN", "bool", "1", "Plan surfaces skip plain fallback"),
            _s("AQUILA_WALKTHROUGH", "bool", "1", "Generate walkthrough on finish"),
            _s("AQUILA_READ_BATCH", "bool", "1", "Batch read tool"),
            _s("AQUILA_RESEARCH_DRAFT_MIN_CHARS", "int", "800", "Research draft min chars"),
            _s("AQUILA_RESEARCH_RECIPE_STRICT", "bool", "0", "Auto-run step capability on entry (QA)", tier=2),
        ),
    ),
    CatalogSection(
        id="dynamic_loop",
        title="Dynamic loop",
        description="Milestone-driven task loop (experimental).",
        tier=2,
        settings=(
            _s("AQUILA_DYNAMIC_LOOP", "bool", "0", "Enable dynamic loop", tier=2),
            _s("AQUILA_AUTO_ADVANCE_MILESTONES", "bool", "0", "Auto-advance milestones", tier=2),
            _s("AQUILA_TASK_EPISODE_MAX", "int", "32", "Task episode max", tier=2),
            _s("AQUILA_TASK_WEB_SEARCH_CAP", "int", "12", "Web search cap per task", tier=2),
            _s("AQUILA_DYNAMIC_SCHEMA_MAX_TOOLS", "int", "128", "Dynamic schema max tools", tier=2),
        ),
    ),
    CatalogSection(
        id="learn_character",
        title="Learn & character",
        description="Temperatures and RAG limits for Learn and Character modes.",
        tier=1,
        settings=(
            _s("AQUILA_CHARACTER_TEMP", "float", "0.8", "Character chat temperature"),
            _s("AQUILA_LEARN_TUTOR_TEMP", "float", "0.7", "Learn tutor temperature"),
            _s("AQUILA_LEARN_ARCHIVE_TEMP", "float", "0.6", "Learn archive temperature"),
            _s("AQUILA_LEARN_ARCHIVE_TOP_K", "int", "5", "Archive RAG top-k"),
            _s("AQUILA_LEARN_TUTOR_TOP_K", "int", "5", "Tutor RAG top-k"),
            _s("AQUILA_LEARN_RETRIEVAL_MAX_CHARS", "int", "12000", "RAG max injected chars"),
            _s("AQUILA_LEARN_ARCHIVE_GENERATION_CAP", "int", "0", "Archive generation cap (sec)"),
        ),
    ),
    CatalogSection(
        id="context_scraping",
        title="Context & scraping",
        description="Web enrichment and context tier for tasks.",
        tier=1,
        settings=(
            _s("AQUILA_AUTO_SCRAPE", "bool", "1", "Auto-scrape search URLs"),
            _s("AQUILA_CONTEXT_TIER", "str", "", "Context tier (standard|extended|max)"),
            _s("AQUILA_TOOL_OUTPUT_CHAR_CAP", "int", "6000", "Tool output char cap"),
            _s("AQUILA_TOTAL_PROMPT_TOKEN_CAP", "int", "8000", "Total prompt token cap"),
        ),
    ),
    CatalogSection(
        id="structured_output",
        title="Structured output",
        description="JSON schema tool calling (see docs/structured-output.md).",
        tier=2,
        settings=(
            _s("AQUILA_STRUCTURED_STRICT", "bool", "1", "Strict schema first", tier=2),
            _s("AQUILA_STRUCTURED_NO_PLAIN", "bool", "0", "Disallow plain fallback", tier=2),
            _s("AQUILA_SCHEMA_MAX_TOOLS", "int", "24", "Max tools in schema", tier=2),
        ),
    ),
    CatalogSection(
        id="ollama_warmup",
        title="Ollama & warmup",
        description="Cold start, warmup, and inference timeouts.",
        tier=2,
        settings=(
            _s("AQUILA_WARMUP_ON_START", "bool", "1", "Warmup on GUI start", tier=2),
            _s("AQUILA_SKIP_WARMUP", "bool", "0", "Skip warmup", tier=2),
            _s("AQUILA_WARMUP_REQUIRED", "bool", "1", "Require warmup success", tier=2),
            _s(
                "AQUILA_EMBEDDING",
                "str",
                "auto",
                "Embedding backend: auto|onnx|hash (auto uses bundled MiniLM, never downloads)",
                tier=2,
            ),
            _s(
                "AQUILA_ALLOW_EMBEDDING_DOWNLOAD",
                "bool",
                "0",
                "Allow downloading MiniLM ONNX if not bundled (off by default)",
                tier=2,
            ),
            _s(
                "AQUILA_EMBEDDINGS_DIR",
                "str",
                "",
                "Override path to runtime/embeddings (contains all-MiniLM-L6-v2/)",
                tier=2,
            ),
            _s(
                "AQUILA_TOOL_INDEX_TIMEOUT_SEC",
                "int",
                "45",
                "Max seconds for tool Chroma indexing",
                tier=2,
            ),
            _s(
                "AQUILA_MCP_CONNECT_TIMEOUT",
                "int",
                "15",
                "Per-server MCP connect timeout (seconds)",
                tier=2,
            ),
            _s("AQUILA_COLD_START_EXTRA_SEC", "int", "90", "Cold start extra seconds", tier=2),
            _s("AQUILA_COLD_START_REQUESTS", "int", "3", "Cold start retry count", tier=2),
            _s("AQUILA_READ_TIMEOUT_MAX", "int", "600", "Max read timeout (sec)", tier=2),
            _s("AQUILA_TIMEOUT_PER_1K_TOKENS", "int", "5", "Timeout per 1k tokens", tier=2),
            _s("AQUILA_TIMEOUT_COMPRESS_RETRY", "bool", "1", "Compress retry on timeout", tier=2),
            _s("AQUILA_EXPECTED_TOKENS_PER_S", "float", "30", "Expected tokens/s (stock)", tier=2),
            _s("AQUILA_TQ_EXPECTED_TOKENS_PER_S", "float", "30", "Expected tokens/s (TQ)", tier=2),
            _s("AQUILA_TQ_PRESET", "str", "tq4", "TurboQuant KV preset", tier=2),
        ),
    ),
    CatalogSection(
        id="stream_guard",
        title="Stream guard",
        description="Repetition detection during streaming.",
        tier=2,
        settings=(
            _s("AQUILA_STREAM_GUARD", "bool", "1", "Enable stream guard", tier=2),
            _s("AQUILA_STREAM_MIN_CHECK_CHARS", "int", "200", "Min chars before check", tier=2),
            _s("AQUILA_STREAM_LINE_REPEAT_MIN", "int", "4", "Min repeated lines", tier=2),
            _s("AQUILA_STREAM_LINE_DOMINANCE", "float", "0.30", "Line dominance threshold", tier=2),
            _s("AQUILA_SLOW_TPS_RATIO", "float", "0.5", "Slow TPS ratio", tier=2),
        ),
    ),
    CatalogSection(
        id="instances_tools",
        title="Instances & tools",
        description="Instance policy and optional tool surfaces.",
        tier=2,
        settings=(
            _s("AQUILA_ACTIVE_INSTANCE", "str", "default", "Active instance id", tier=2),
            _s("AQUILA_CONVERSATION_ARCHIVE", "bool", "1", "Conversation archive", tier=2),
            _s("AQUILA_DIFF_REVIEW", "bool", "1", "Diff review in Code Canvas", tier=2),
            _s("AQUILA_TERMINAL", "bool", "0", "Enable terminal tool", tier=2),
            _s("AQUILA_RUN_COMMAND", "bool", "1", "Enable run_command tool", tier=2),
            _s("AQUILA_ENABLE_DATA_PROCESSING", "bool", "0", "Data processing mode", tier=2),
            _s("AQUILA_DATA_MAX_FILE_MB", "int", "50", "Data max file MB", tier=2),
            _s("AQUILA_DATA_MAX_CSV_ROWS", "int", "200", "Data max CSV rows", tier=2),
            _s("AQUILA_MCP_DELIVERABLE_CAP", "int", "12000", "MCP deliverable read cap", tier=2),
            _s(
                "AQUILA_MCP_ALLOWED_MODES",
                "str",
                "autonomous,task,research,code,writing",
                "MCP allowed modes (comma list)",
                tier=2,
            ),
        ),
    ),
    CatalogSection(
        id="logging",
        title="Logging",
        description="Run logs and JSONL events.",
        tier=2,
        settings=(
            _s("AQUILA_LOG_JSON", "bool", "1", "JSONL event log", tier=2),
            _s("AQUILA_LOG_FULL_TOOLS", "bool", "0", "Log full tool payloads", tier=2),
        ),
    ),
    CatalogSection(
        id="email_smtp",
        title="Email (SMTP)",
        description="Optional send_email tool credentials.",
        tier=1,
        settings=(
            _s("SMTP_SERVER", "str", "", "SMTP server", export_env=True),
            _s("SMTP_PORT", "int", "587", "SMTP port"),
            _s("SMTP_USER", "str", "", "SMTP user"),
            _s("SMTP_PASSWORD", "str", "", "SMTP password"),
            _s("SMTP_USE_TLS", "bool", "1", "Use TLS"),
        ),
    ),
    CatalogSection(
        id="ollama_connection",
        title="Ollama connection (export)",
        description="Also edited on AI Engine page; exported to .env for shell scripts.",
        tier=1,
        settings=(
            _s("OLLAMA_BASE_URL", "str", "http://127.0.0.1:11434", "Ollama base URL"),
            _s("OLLAMA_MODEL", "str", "aquila_qwopus", "Ollama model"),
            _s("OLLAMA_NUM_CTX", "int", "", "Ollama num_ctx (empty=default)"),
            _s("OLLAMA_KEEP_ALIVE", "str", "30m", "Ollama keep_alive"),
        ),
    ),
    CatalogSection(
        id="searxng_connection",
        title="SearXNG (export)",
        description="Also edited on Web Search page.",
        tier=1,
        settings=(
            _s("SEARXNG_BASE_URL", "str", "http://127.0.0.1:8080", "SearXNG base URL"),
            _s(
                "SEARXNG_ENGINES",
                "str",
                "google,bing,duckduckgo,wikipedia",
                "SearXNG engines",
            ),
        ),
    ),
)


def load_catalog() -> tuple[CatalogSection, ...]:
    return CATALOG_SECTIONS


def catalog_settings() -> dict[str, SettingDef]:
    out: dict[str, SettingDef] = {}
    for section in CATALOG_SECTIONS:
        for setting in section.settings:
            out[setting.key] = setting
    return out


def catalog_defaults() -> dict[str, str]:
    return {k: v.default for k, v in catalog_settings().items()}


def catalog_sections_for_gui(*, include_advanced: bool = True) -> list[CatalogSection]:
    sections: list[CatalogSection] = []
    for section in CATALOG_SECTIONS:
        if section.id in ("email_smtp", "ollama_connection", "searxng_connection"):
            continue
        if not include_advanced and section.tier > 1:
            continue
        sections.append(section)
    return sections


def validate_value(defn: SettingDef, raw: str) -> str:
    val = (raw or "").strip()
    if defn.type == "bool":
        low = val.lower()
        if low in ("1", "true", "yes", "on"):
            return "1"
        if low in ("0", "false", "no", "off", ""):
            return "0"
        raise ValueError(f"{defn.key}: expected bool (0/1)")
    if defn.type == "int":
        if not val:
            return defn.default if defn.default else ""
        if not re.fullmatch(r"-?\d+", val):
            raise ValueError(f"{defn.key}: expected integer")
        return val
    if defn.type == "float":
        if not val:
            return defn.default
        try:
            float(val)
        except ValueError as exc:
            raise ValueError(f"{defn.key}: expected number") from exc
        return val
    return val


def exportable_keys() -> frozenset[str]:
    return frozenset(
        k for k, d in catalog_settings().items() if d.export_env and k not in INTERNAL_KEYS
    )


def generate_env_example() -> str:
    """Build .env.EXAMPLE content from the catalog."""
    lines: list[str] = []
    for section in CATALOG_SECTIONS:
        if section.id in ("email_smtp",):
            lines.append("")
            continue
        lines.append("")
        lines.append(f"# {section.title} — {section.description}")
        for setting in section.settings:
            if setting.key in INTERNAL_KEYS:
                continue
            if setting.description:
                lines.append(f"# {setting.description}")
            if setting.default:
                lines.append(f"# {setting.key}={setting.default}")
            else:
                lines.append(f"# {setting.key}=")
    # SMTP block at top (active values for copy-paste)
    smtp = next(s for s in CATALOG_SECTIONS if s.id == "email_smtp")
    header: list[str] = []
    for setting in smtp.settings:
        header.append(f"{setting.key}=")
    header.append("")
    header.append("# Ollama — see Settings → AI Engine or docs/ollama-dual-setup.md")
    header.append("OLLAMA_BASE_URL=http://127.0.0.1:11434")
    header.append("OLLAMA_MODEL=aquila_qwopus")
    header.append("")
    return "\n".join(header + lines).strip() + "\n"


def write_env_example(path: Path | None = None) -> Path:
    target = path or (REPO_ROOT / ".env.EXAMPLE")
    target.write_text(generate_env_example(), encoding="utf-8")
    return target
