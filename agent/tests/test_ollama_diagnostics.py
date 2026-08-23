import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.parser import (
    chars_to_estimated_tokens,
    estimate_tokens_metrics,
    format_diagnostics_summary,
    measure_streaming_response,
    parse_nvidia_smi_csv_line,
)


def test_chars_to_estimated_tokens_basic():
    assert chars_to_estimated_tokens("", chars_per_token=4.0) == 1
    assert chars_to_estimated_tokens("aaaa", chars_per_token=4.0) == 1
    assert chars_to_estimated_tokens("aaaaaaaa", chars_per_token=4.0) == 2


def test_estimate_tokens_metrics_tokens_per_s():
    tokens, tps = estimate_tokens_metrics("aaaaaa", duration_s=2.0, chars_per_token=3.0)
    # 6 chars / 3 chars/token => 2 tokens
    assert tokens == 2
    assert tps == pytest.approx(1.0)


def test_parse_nvidia_smi_csv_line_parses_ints():
    s = parse_nvidia_smi_csv_line("100, 200, 50, 60, 70")
    assert s.memory_used_mib == 100
    assert s.memory_total_mib == 200
    assert s.utilization_gpu_percent == 50
    assert s.temperature_gpu_c == 60
    assert s.power_draw_w == 70


def test_parse_nvidia_smi_csv_line_invalid_returns_empty_sample():
    s = parse_nvidia_smi_csv_line("nonsense")
    assert s.memory_used_mib is None
    assert s.memory_total_mib is None
    assert s.utilization_gpu_percent is None


def test_measure_streaming_response_counts_thinking_stream():
    token_stream = [
        {"message": {"thinking": "hello"}},
        {"message": {"thinking": " world"}},
    ]
    output_text, ttft_s, duration_s = measure_streaming_response(
        token_stream, time_fn=lambda: 0.0
    )
    assert output_text == "hello world"
    assert ttft_s == 0.0


def test_measure_streaming_response_ttft_and_duration_with_fake_time():
    token_stream = [
        {"message": {"content": "hello"}},
        {"message": {"content": " world"}},
    ]
    times = [0.0, 1.25, 2.5]

    def fake_time_fn():
        return times.pop(0)

    output_text, ttft_s, duration_s = measure_streaming_response(
        token_stream, time_fn=fake_time_fn
    )
    assert output_text == "hello world"
    assert ttft_s == pytest.approx(1.25)
    assert duration_s == pytest.approx(2.5)


def test_format_diagnostics_summary_contains_keys():
    result = {
        "ollama_reachable": True,
        "ollama_model_present": True,
        "runs": [
            {
                "duration_s": 3.0,
                "ttft_s": 1.0,
                "estimated_tokens_per_s": 42.0,
                "anomalies": {"spillover_suspected": True},
            }
        ],
    }
    text = format_diagnostics_summary(result)
    assert "Ollama Diagnostics Summary" in text
    assert "reachable: True" in text
    assert "model_present: True" in text
    assert "spillover_suspected" in text

