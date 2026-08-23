"""Model setup helpers (mocked ollama)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.aquila_runtime.hardware_profile import HardwareProfile
from agent.aquila_runtime.model_setup import ensure_recommended_model, modelfile_for_profile


def test_modelfile_for_profile_lite():
    prof = HardwareProfile(
        id="cpu_only",
        label="CPU",
        modelfile_name="Modelfile.lite",
        pull_tag="qwen2.5:3b",
        default_model="aquila-lite",
    )
    path = modelfile_for_profile(prof)
    assert path.name == "Modelfile.lite"
    assert path.is_file()


@patch("agent.aquila_runtime.model_setup._run_ollama")
def test_ensure_recommended_model_nvidia_low_with_full(mock_run):
    mock_run.side_effect = [
        (True, "lite pulled"),
        (True, "lite created"),
        (True, "full pulled"),
        (True, "full created"),
    ]
    prof = HardwareProfile(
        id="nvidia_low",
        label="NVIDIA low",
        default_model="aquila-lite",
        pull_tag="qwen2.5:3b",
        modelfile_name="Modelfile.lite",
        offer_full_model=True,
        full_modelfile_name="Modelfile.low-vram",
    )
    ok, msg = ensure_recommended_model(prof, include_full_model=True)
    assert ok is True
    assert mock_run.call_count == 4
    assert mock_run.call_args_list[3][0][0][1] == "aquila"
    path_arg = mock_run.call_args_list[3][0][0][3]
    assert "Modelfile.low-vram" in path_arg or path_arg.endswith("Modelfile.low-vram")


@patch("agent.aquila_runtime.model_setup._run_ollama")
def test_ensure_recommended_model_gpu_pull_and_create(mock_run):
    mock_run.side_effect = [
        (True, "pulled"),
        (True, "created"),
    ]
    prof = HardwareProfile(
        id="nvidia_mid",
        label="GPU",
        default_model="aquila_qwopus",
        pull_tag="hf.co/Jackrong/Qwopus3.5-9B-Coder-GGUF:Q4_K_M",
        modelfile_name="Modelfile.Qwopus",
    )
    ok, msg = ensure_recommended_model(prof)
    assert ok is True
    assert mock_run.call_count == 2
    assert mock_run.call_args_list[0][0][0] == [
        "pull",
        "hf.co/Jackrong/Qwopus3.5-9B-Coder-GGUF:Q4_K_M",
    ]
    create_args = mock_run.call_args_list[1][0][0]
    assert create_args[0:2] == ["create", "aquila_qwopus"]


@patch("agent.aquila_runtime.model_setup._run_ollama")
def test_ensure_recommended_model_lite_cpu(mock_run):
    mock_run.side_effect = [
        (True, "pulled"),
        (True, "created"),
    ]
    prof = HardwareProfile(
        id="cpu_only",
        label="CPU",
        default_model="aquila-lite",
        pull_tag="qwen2.5:3b",
        modelfile_name="Modelfile.lite",
    )
    ok, msg = ensure_recommended_model(prof)
    assert ok is True
    assert "aquila-lite" in msg
    assert mock_run.call_args_list[0][0][0] == ["pull", "qwen2.5:3b"]
    assert mock_run.call_args_list[1][0][0][1] == "aquila-lite"


@patch("agent.aquila_runtime.model_setup._run_ollama")
def test_ensure_recommended_model_cpu_with_full(mock_run):
    mock_run.side_effect = [
        (True, "lite pulled"),
        (True, "lite created"),
        (True, "full pulled"),
        (True, "full created"),
    ]
    prof = HardwareProfile(
        id="cpu_only",
        label="CPU",
        default_model="aquila-lite",
        pull_tag="qwen2.5:3b",
        modelfile_name="Modelfile.lite",
        offer_full_model=True,
        full_modelfile_name="Modelfile.cpu",
    )
    ok, msg = ensure_recommended_model(prof, include_full_model=True)
    assert ok is True
    assert mock_run.call_count == 4
    assert mock_run.call_args_list[2][0][0] == ["pull", "qwen3.5:9b"]
    assert mock_run.call_args_list[3][0][0][1] == "aquila"


@patch("agent.aquila_runtime.ollama_bundle.ensure_packaged_ollama")
@patch("agent.aquila_runtime.model_setup.packaged_ollama_binary")
@patch("agent.aquila_runtime.model_setup.popen_hidden")
def test_run_ollama_reads_utf8_stdout(mock_popen, mock_binary, mock_ensure, tmp_path):
    from agent.aquila_runtime.model_setup import _run_ollama

    binary = tmp_path / "ollama.exe"
    binary.write_text("", encoding="utf-8")
    mock_ensure.return_value = (True, "ok")
    mock_binary.return_value = binary

    proc = MagicMock()
    proc.stdout = iter(["pulling manifest\n", "success\n"])
    proc.wait.return_value = 0
    mock_popen.return_value = proc

    ok, msg = _run_ollama(["pull", "qwen3.5:9b"])
    assert ok is True
    kwargs = mock_popen.call_args.kwargs
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    assert kwargs["cwd"] == str(binary.parent)


def test_sanitize_cli_progress_strips_ansi():
    from agent.aquila_runtime.model_setup import sanitize_cli_progress

    raw = "\x1b[1Gpulling manifest \x1b[K\x1b[?25h\x1b[?2026l"
    assert sanitize_cli_progress(raw) == "pulling manifest"
    bar = "pulling dec52a44569a: 38%\x1b[K | 2.5 GB/6.6 GB  75 MB/s   54s"
    assert "38%" in sanitize_cli_progress(bar)
    assert "\x1b" not in sanitize_cli_progress(bar)
