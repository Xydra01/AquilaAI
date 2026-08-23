"""Ollama diagnostics: TTFT, estimated tokens/s, and GPU/VRAM sampling.

Designed to help distinguish:
- Ollama unreachable / model not loaded
- VRAM loading stalls (high TTFT, low utilization)
- Output throughput collapse (low tokens/s)
- Possible VRAM spillover to shared/CPU (GPU memory trend vs Ollama RSS)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Generator, Iterable, Iterator, List, Optional

import psutil


try:
    # Reuse Aquila's client so streaming and timeouts match.
    from agent.core import OllamaClient
except Exception:  # pragma: no cover - import guard for tool-less environments
    OllamaClient = None  # type: ignore


@dataclass(frozen=True)
class GpuSample:
    ts_s: float
    memory_used_mib: Optional[int] = None
    memory_total_mib: Optional[int] = None
    utilization_gpu_percent: Optional[int] = None
    temperature_gpu_c: Optional[int] = None
    power_draw_w: Optional[int] = None


@dataclass(frozen=True)
class ProcessSample:
    ts_s: float
    rss_mib: Optional[float] = None
    cpu_percent: Optional[float] = None


@dataclass
class DiagnosticsRun:
    started_ts_s: float
    finished_ts_s: float
    duration_s: float
    ttft_s: Optional[float]
    prompt: str
    model: str
    num_ctx: Optional[int]
    output_text: str
    estimated_output_tokens: int
    estimated_tokens_per_s: Optional[float]
    ollama_reachable: bool
    ollama_model_present: Optional[bool]
    gpu_samples: list[GpuSample] = field(default_factory=list)
    process_samples: list[ProcessSample] = field(default_factory=list)
    anomalies: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_ts_s": self.started_ts_s,
            "finished_ts_s": self.finished_ts_s,
            "duration_s": self.duration_s,
            "ttft_s": self.ttft_s,
            "prompt": self.prompt,
            "model": self.model,
            "num_ctx": self.num_ctx,
            "output_text_preview": (self.output_text or "")[:200],
            "estimated_output_tokens": self.estimated_output_tokens,
            "estimated_tokens_per_s": self.estimated_tokens_per_s,
            "ollama_reachable": self.ollama_reachable,
            "ollama_model_present": self.ollama_model_present,
            "gpu_samples": [asdict(s) for s in self.gpu_samples],
            "process_samples": [asdict(s) for s in self.process_samples],
            "anomalies": self.anomalies,
        }


@dataclass
class DiagnosticsConfig:
    trials: int = 1
    prompt: str = "pong"
    stream: bool = True
    eject_between_trials: bool = False
    warmup_before_trials: bool = True
    chars_per_token: float = 4.0
    # GPU sampling
    gpu_sampling_enabled: bool = True
    gpu_sample_interval_s: float = 0.75
    # Process sampling
    process_sampling_enabled: bool = True
    process_sample_interval_s: float = 0.75
    # How to detect the Ollama process
    ollama_process_name_contains: tuple[str, ...] = ("ollama",)
    # Heuristics thresholds
    high_ttft_s: float = 8.0
    low_utilization_percent: int = 5
    low_tokens_per_s: float = 10.0


_NVIDIA_SMI_CSV_LINE_RE = re.compile(r"^\s*([^,]+)\s*,([^,]+)\s*,([^,]+)\s*,([^,]+)\s*,([^,]+)\s*$")


def chars_to_estimated_tokens(chars: str, *, chars_per_token: float = 4.0) -> int:
    """Heuristic: consistent with `scripts/benchmark_context.py`."""
    n_chars = len(chars or "")
    if chars_per_token <= 0:
        return n_chars
    return max(1, int(n_chars / float(chars_per_token)))


def parse_nvidia_smi_csv_line(line: str) -> GpuSample:
    """Parse one `nvidia-smi --format=csv,noheader,nounits` line.

    Expected columns (in order):
      memory.used, memory.total, utilization.gpu, temperature.gpu, power.draw
    """
    ts = time.perf_counter()
    m = _NVIDIA_SMI_CSV_LINE_RE.match((line or "").strip())
    if not m:
        return GpuSample(ts_s=ts)

    def _to_int(s: str) -> Optional[int]:
        s = (s or "").strip()
        if not s:
            return None
        try:
            return int(float(s))
        except ValueError:
            return None

    mem_used = _to_int(m.group(1))
    mem_total = _to_int(m.group(2))
    util = _to_int(m.group(3))
    temp = _to_int(m.group(4))
    power = _to_int(m.group(5))
    return GpuSample(
        ts_s=ts,
        memory_used_mib=mem_used,
        memory_total_mib=mem_total,
        utilization_gpu_percent=util,
        temperature_gpu_c=temp,
        power_draw_w=power,
    )


def is_nvidia_smi_available() -> bool:
    return shutil.which("nvidia-smi") is not None


def run_nvidia_smi_query_once() -> str | None:
    """Return raw CSV line(s) or None if nvidia-smi unavailable."""
    if not is_nvidia_smi_available():
        return None
    query = (
        "memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw"
    )
    cmd = [
        "nvidia-smi",
        f"--query-gpu={query}",
        "--format=csv,noheader,nounits",
    ]
    try:
        out = subprocess.check_output(cmd, timeout=3)
        return out.decode("utf-8", errors="replace").strip()
    except Exception:
        return None


def estimate_tokens_metrics(
    output_text: str,
    *,
    duration_s: float,
    chars_per_token: float = 4.0,
) -> tuple[int, Optional[float]]:
    tokens = chars_to_estimated_tokens(output_text, chars_per_token=chars_per_token)
    if duration_s <= 0:
        return tokens, None
    return tokens, tokens / float(duration_s)


def _find_ollama_pids(name_contains: tuple[str, ...]) -> list[int]:
    lowered = tuple(s.lower() for s in name_contains)
    pids: list[int] = []
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            name = (proc.info.get("name") or "").lower()
            if any(substr in name for substr in lowered):
                pids.append(int(proc.info["pid"]))
    except Exception:
        return []
    return pids


def _ollama_rss_mib(pid: int) -> Optional[float]:
    try:
        p = psutil.Process(pid)
        rss_bytes = p.memory_info().rss
        return rss_bytes / (1024.0 * 1024.0)
    except Exception:
        return None


def _ollama_cpu_percent(pid: int) -> Optional[float]:
    try:
        p = psutil.Process(pid)
        # cpu_percent requires a prior call to establish baseline; we still use it.
        return float(p.cpu_percent(interval=None))
    except Exception:
        return None


def build_anomalies(
    *,
    ttft_s: Optional[float],
    estimated_tokens_per_s: Optional[float],
    gpu_samples: list[GpuSample],
    process_samples: list[ProcessSample],
    high_ttft_s: float,
    low_utilization_percent: int,
    low_tokens_per_s: float,
) -> dict[str, Any]:
    anomalies: dict[str, Any] = {}

    if ttft_s is not None and ttft_s >= high_ttft_s:
        anomalies["high_ttft_suspected"] = True
        anomalies["high_ttft_s"] = ttft_s

    util_samples = [s.utilization_gpu_percent for s in gpu_samples if s.utilization_gpu_percent is not None]
    if util_samples and util_samples[0] is not None:
        median_util = sorted(util_samples)[len(util_samples) // 2]
        anomalies["gpu_utilization_median_percent"] = median_util
        if median_util <= low_utilization_percent and (ttft_s or 0) >= (high_ttft_s * 0.75):
            anomalies["low_utilization_with_high_ttft"] = True

    if estimated_tokens_per_s is not None and estimated_tokens_per_s <= low_tokens_per_s:
        anomalies["low_tokens_per_s_suspected"] = True
        anomalies["estimated_tokens_per_s"] = estimated_tokens_per_s

    # Possible spillover heuristic: GPU memory used decreases while RSS increases.
    mem_used = [s.memory_used_mib for s in gpu_samples if s.memory_used_mib is not None]
    rss = [s.rss_mib for s in process_samples if s.rss_mib is not None]
    if mem_used and rss and len(mem_used) >= 2 and len(rss) >= 2:
        mem_delta = mem_used[-1] - mem_used[0]
        rss_delta = rss[-1] - rss[0]
        anomalies["spillover_mem_delta_mib"] = mem_delta
        anomalies["spillover_rss_delta_mib"] = rss_delta
        if mem_delta < 0 and rss_delta > 0:
            anomalies["spillover_suspected"] = True

    return anomalies


def measure_streaming_response(
    token_stream: Iterable[dict[str, Any]],
    *,
    time_fn: Callable[[], float] = time.perf_counter,
) -> tuple[str, Optional[float], float]:
    """Consume an iterable of token dicts, returning (output_text, ttft_s, duration_s)."""
    started = time_fn()
    ttft: Optional[float] = None
    output_parts: list[str] = []
    first_token_seen = False

    for chunk in token_stream:
        token = ""
        try:
            msg = (chunk or {}).get("message") or {}
            token = msg.get("content") or ""
            # TurboQuant / Qwen may stream answer in `thinking` with empty content.
            if not token:
                token = msg.get("thinking") or ""
        except Exception:
            token = ""
        if token and not first_token_seen:
            ttft = time_fn() - started
            first_token_seen = True
        if token:
            output_parts.append(token)
    finished = time_fn()
    return "".join(output_parts), ttft, finished - started


def _stream_chat_tokens(
    client: Any,
    *,
    prompt: str,
    model: str,
    num_ctx: Optional[int],
    timeout_s: int = 0,
) -> Iterable[dict[str, Any]]:
    """Invoke Aquila's OllamaClient streaming path, yielding token dicts."""
    # OllamaClient.chat() accepts `messages` not a raw prompt.
    messages = [{"role": "system", "content": "You are Aquila diagnostics."}, {"role": "user", "content": prompt}]
    # Note: Aquila's OllamaClient uses `timeout` as generation kill-switch seconds.
    return client.chat(
        messages=messages,
        stream=True,
        format=None,
        timeout=timeout_s,
        estimated_prompt_tokens=200,
        keep_alive=None,
    )


def quick_throughput_probe(
    client: Any,
    *,
    prompt: str = "Reply with one short sentence.",
    warmup: bool = False,
    timeout_s: int = 120,
    baseline_tokens_per_s: float | None = None,
) -> dict[str, Any]:
    """Stream a short reply on the given client; return TTFT and est. tokens/s."""
    from agent.storage import engine_for_base_url, expected_tokens_per_s

    base_url = getattr(client, "base_url", "") or ""
    model = getattr(client, "model_name", "") or ""
    num_ctx = getattr(client, "num_ctx", None)
    engine = engine_for_base_url(base_url) or "unknown"
    baseline = (
        baseline_tokens_per_s
        if baseline_tokens_per_s is not None
        else expected_tokens_per_s(engine, base_url=base_url)
    )

    if not bool(getattr(client, "probe", lambda: False)()):
        return {
            "ok": False,
            "ollama_engine": engine,
            "ollama_base_url": base_url,
            "error": f"Ollama not reachable at {base_url}",
        }

    if warmup:
        try:
            client.warmup()
        except Exception:
            pass

    try:
        stream = _stream_chat_tokens(
            client,
            prompt=prompt,
            model=model,
            num_ctx=num_ctx,
            timeout_s=timeout_s,
        )
        output_text, ttft_s, duration_s = measure_streaming_response(stream)
    except Exception as exc:
        return {
            "ok": False,
            "ollama_engine": engine,
            "ollama_base_url": base_url,
            "model": model,
            "error": str(exc),
        }

    if duration_s < 0.05 or not (output_text or "").strip():
        return {
            "ok": False,
            "ollama_engine": engine,
            "ollama_base_url": base_url,
            "model": model,
            "num_ctx": num_ctx,
            "error": "No streamed output (check model load / TQ thinking stream).",
            "duration_s": duration_s,
            "ttft_s": ttft_s,
        }

    est_tokens, tps = estimate_tokens_metrics(output_text, duration_s=duration_s)
    health = "ok"
    if tps is not None:
        if tps < baseline * 0.5:
            health = "slow"
        elif tps < baseline * 0.85:
            health = "degraded"
    return {
        "ok": True,
        "ollama_engine": engine,
        "ollama_base_url": base_url,
        "model": model,
        "num_ctx": num_ctx,
        "baseline_tokens_per_s": baseline,
        "estimated_output_tokens": est_tokens,
        "estimated_tokens_per_s": round(tps, 2) if tps is not None else None,
        "ttft_s": round(ttft_s, 3) if ttft_s is not None else None,
        "duration_s": round(duration_s, 3),
        "health": health,
    }


def get_ollama_presence(client: Any) -> bool:
    names = client.list_loaded_models()
    model_name = getattr(client, "model_name", "") or ""
    if not model_name:
        return False
    return any(model_name in n for n in names)


def run_ollama_diagnostics(
    config: DiagnosticsConfig,
    *,
    out_json_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run diagnostics for `trials` and return a result dict."""
    if OllamaClient is None:
        raise RuntimeError("OllamaClient import failed; cannot run diagnostics.")

    client = OllamaClient()
    model = getattr(client, "model_name", "") or os.getenv("OLLAMA_MODEL", "aquila")
    num_ctx = getattr(client, "num_ctx", None)

    reachable = bool(client.probe())
    model_present: Optional[bool] = None
    if reachable:
        model_present = get_ollama_presence(client)

    if config.warmup_before_trials and reachable:
        # Warmup helps isolate TTFT variance; this is optional.
        client.warmup()

    runs: list[DiagnosticsRun] = []

    for trial in range(config.trials):
        if config.eject_between_trials and reachable:
            client.eject_model(model)

        started = time.perf_counter()
        gpu_samples: list[GpuSample] = []
        process_samples: list[ProcessSample] = []

        stop_event = threading.Event()
        pids = _find_ollama_pids(config.ollama_process_name_contains)

        def gpu_sampler() -> None:
            if not config.gpu_sampling_enabled or not is_nvidia_smi_available():
                return
            # Wait until streaming has started so the first sample aligns better.
            while not stop_event.is_set():
                line = run_nvidia_smi_query_once()
                if line:
                    # nvidia-smi may output multiple lines; parse the first line.
                    first = (line.splitlines() or [""])[0]
                    gpu_samples.append(parse_nvidia_smi_csv_line(first))
                time.sleep(config.gpu_sample_interval_s)

        def proc_sampler() -> None:
            if not config.process_sampling_enabled:
                return
            if not pids:
                return
            while not stop_event.is_set():
                # sample the first matching pid (usually enough for ollama.exe)
                pid = pids[0]
                rss = _ollama_rss_mib(pid)
                cpu = _ollama_cpu_percent(pid)
                process_samples.append(ProcessSample(ts_s=time.perf_counter(), rss_mib=rss, cpu_percent=cpu))
                time.sleep(config.process_sample_interval_s)

        t_gpu: Optional[threading.Thread] = None
        t_proc: Optional[threading.Thread] = None
        if config.gpu_sampling_enabled:
            t_gpu = threading.Thread(target=gpu_sampler, daemon=True)
            t_gpu.start()
        if config.process_sampling_enabled:
            t_proc = threading.Thread(target=proc_sampler, daemon=True)
            t_proc.start()

        try:
            token_stream = _stream_chat_tokens(
                client,
                prompt=config.prompt,
                model=model,
                num_ctx=num_ctx,
                timeout_s=0,
            )
            output_text, ttft_s, duration_s = measure_streaming_response(token_stream)
        finally:
            stop_event.set()
            # Give samplers a beat to exit.
            time.sleep(0.05)

        estimated_tokens, tokens_per_s = estimate_tokens_metrics(
            output_text,
            duration_s=duration_s,
            chars_per_token=config.chars_per_token,
        )

        anomalies = build_anomalies(
            ttft_s=ttft_s,
            estimated_tokens_per_s=tokens_per_s,
            gpu_samples=gpu_samples,
            process_samples=process_samples,
            high_ttft_s=config.high_ttft_s,
            low_utilization_percent=config.low_utilization_percent,
            low_tokens_per_s=config.low_tokens_per_s,
        )

        runs.append(
            DiagnosticsRun(
                started_ts_s=started,
                finished_ts_s=time.perf_counter(),
                duration_s=duration_s,
                ttft_s=ttft_s,
                prompt=config.prompt,
                model=model,
                num_ctx=num_ctx,
                output_text=output_text,
                estimated_output_tokens=estimated_tokens,
                estimated_tokens_per_s=tokens_per_s,
                ollama_reachable=reachable,
                ollama_model_present=model_present,
                gpu_samples=gpu_samples,
                process_samples=process_samples,
                anomalies=anomalies,
            )
        )

    result: dict[str, Any] = {
        "config": asdict(config),
        "ollama_reachable": reachable,
        "ollama_model_present": model_present,
        "runs": [r.to_dict() for r in runs],
    }

    if out_json_path:
        out_path = Path(out_json_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return result


def format_diagnostics_summary(result: dict[str, Any]) -> str:
    runs = result.get("runs") or []
    if not runs:
        return "No runs executed."
    # Summarize using first run (common for a single trial).
    r0 = runs[0]
    lines: list[str] = []
    lines.append("Ollama Diagnostics Summary")
    lines.append(f"  reachable: {result.get('ollama_reachable')}")
    lines.append(f"  model_present: {result.get('ollama_model_present')}")
    lines.append(f"  trials: {len(runs)}")

    for i, r in enumerate(runs, start=1):
        lines.append(f"  Run {i}: duration={r.get('duration_s'):.2f}s ttft={r.get('ttft_s')}s tokens/s={r.get('estimated_tokens_per_s')}")
        anomalies = r.get("anomalies") or {}
        if anomalies:
            lines.append(f"    anomalies: {anomalies}")

    return "\n".join(lines)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def build_cli_config_from_args(args: dict[str, Any]) -> DiagnosticsConfig:
    return DiagnosticsConfig(
        trials=int(args.get("trials", 1)),
        prompt=str(args.get("prompt", "pong")),
        eject_between_trials=bool(args.get("eject_between_trials", False)),
        warmup_before_trials=bool(args.get("warmup_before_trials", False)),
        gpu_sampling_enabled=bool(args.get("gpu_sampling_enabled", True)),
        gpu_sample_interval_s=float(args.get("gpu_sample_interval_s", 0.75)),
        process_sampling_enabled=bool(args.get("process_sampling_enabled", True)),
        process_sample_interval_s=float(
            args.get("process_sample_interval_s", 0.75)
        ),
        chars_per_token=float(args.get("chars_per_token", 4.0)),
        high_ttft_s=float(args.get("high_ttft_s", 8.0)),
        low_utilization_percent=int(args.get("low_utilization_percent", 5)),
        low_tokens_per_s=float(args.get("low_tokens_per_s", 10.0)),
    )


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Aquila Ollama diagnostics tool.")
    parser.add_argument("--trials", type=int, default=int(os.getenv("AQUILA_DIAG_TRIALS", "1")))
    parser.add_argument("--prompt", type=str, default=os.getenv("AQUILA_DIAG_PROMPT", "pong"))
    parser.add_argument(
        "--json-path",
        type=str,
        default=os.getenv("AQUILA_DIAG_JSON_PATH", ""),
        help="Write JSON output to this path (optional).",
    )
    parser.add_argument(
        "--eject-between-trials",
        action="store_true",
        default=_bool_env("AQUILA_DIAG_EJECT_BETWEEN_TRIALS", False),
    )
    parser.add_argument(
        "--warmup-before-trials",
        action="store_true",
        default=_bool_env("AQUILA_DIAG_WARMUP_BEFORE_TRIALS", False),
    )
    parser.add_argument(
        "--no-gpu-sampling",
        action="store_true",
        default=False,
        help="Disable nvidia-smi sampling.",
    )
    parser.add_argument(
        "--no-process-sampling",
        action="store_true",
        default=False,
        help="Disable psutil Ollama process sampling.",
    )
    parser.add_argument("--gpu-interval-s", type=float, default=0.75)
    parser.add_argument("--proc-interval-s", type=float, default=0.75)
    parser.add_argument("--chars-per-token", type=float, default=4.0)

    args = parser.parse_args(argv)
    cfg = build_cli_config_from_args(
        {
            "trials": args.trials,
            "prompt": args.prompt,
            "eject_between_trials": args.eject_between_trials,
            "warmup_before_trials": args.warmup_before_trials,
            "gpu_sampling_enabled": not args.no_gpu_sampling,
            "process_sampling_enabled": not args.no_process_sampling,
            "gpu_sample_interval_s": args.gpu_interval_s,
            "process_sample_interval_s": args.proc_interval_s,
            "chars_per_token": args.chars_per_token,
        }
    )

    out_json_path = args.json_path.strip() or None
    result = run_ollama_diagnostics(cfg, out_json_path=out_json_path)
    summary = format_diagnostics_summary(result)
    print(summary)
    return 0 if result.get("ollama_reachable") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

