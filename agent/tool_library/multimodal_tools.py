"""Local multimodal tools (Vision via Ollama/LLaVA, Audio via Whisper, Video via FFmpeg)."""
from __future__ import annotations

import os
import json
import base64
import urllib.request
import urllib.error
import subprocess
import tempfile
import inspect
from typing import Any

from agent.core import format_tool_result


def analyze_image_local(image_path: str, prompt: str) -> str:
    """
    Analyze a local image using a local vision model (e.g. LLaVA via Ollama).
    USE WHEN: You need to understand the visual contents of a UI screenshot or diagram.
    """
    if not os.path.exists(image_path):
        return format_tool_result("ERROR", "analyze_image_local", f"File not found: {image_path}")

    try:
        with open(image_path, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return format_tool_result("ERROR", "analyze_image_local", f"Failed to read image: {e}")

    payload = {
        "model": "llava",
        "prompt": prompt,
        "images": [b64_img],
        "stream": False,
        "keep_alive": 0  # Unload immediately after generation to save VRAM
    }
    
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=json.dumps(payload).encode("utf-8"))
    req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("response", "")
    except urllib.error.URLError as e:
        return format_tool_result("ERROR", "analyze_image_local", 
            f"Could not connect to Ollama. Ensure Ollama is running and 'llava' is installed (ollama run llava). Error: {e}"
        )
    except Exception as e:
        return format_tool_result("ERROR", "analyze_image_local", f"Vision analysis failed: {e}")


def transcribe_audio_local(audio_path: str) -> str:
    """
    Transcribe a local audio file to text using a local Whisper model.
    USE WHEN: You need to ingest voice notes or meeting recordings locally.
    """
    if not os.path.exists(audio_path):
        return format_tool_result("ERROR", "transcribe_audio_local", f"File not found: {audio_path}")

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # We assume `whisper` is available on the system PATH
            cmd = [
                "whisper",
                audio_path,
                "--output_format", "txt",
                "--output_dir", temp_dir,
                "--model", "base"  # Use base model as default for speed
            ]
            # Capture output so it doesn't pollute the main terminal unless necessary
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            # Find the resulting .txt file
            base_name = os.path.splitext(os.path.basename(audio_path))[0]
            txt_path = os.path.join(temp_dir, f"{base_name}.txt")
            
            if os.path.exists(txt_path):
                with open(txt_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            else:
                return format_tool_result("ERROR", "transcribe_audio_local", "Transcription output file was not generated.")
                
        except FileNotFoundError:
            return format_tool_result("ERROR", "transcribe_audio_local", 
                "The 'whisper' CLI command was not found. Please install whisper (e.g. `pip install -U openai-whisper` and `ffmpeg`)."
            )
        except subprocess.CalledProcessError as e:
            return format_tool_result("ERROR", "transcribe_audio_local", f"Whisper transcription failed: {e.stderr}")
        except Exception as e:
            return format_tool_result("ERROR", "transcribe_audio_local", f"Unexpected error: {e}")


def analyze_video_local(video_path: str) -> str:
    """
    Analyze a video file by extracting audio for Whisper transcription and keyframes for LLaVA visual analysis.
    USE WHEN: You need to understand the contents of a local video file.
    """
    if not os.path.exists(video_path):
        return format_tool_result("ERROR", "analyze_video_local", f"File not found: {video_path}")

    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return format_tool_result("ERROR", "analyze_video_local", 
            "imageio-ffmpeg is not installed. Run `pip install imageio-ffmpeg` to use video analysis."
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        # 1. Extract audio to wav
        audio_path = os.path.join(temp_dir, "extracted_audio.wav")
        audio_cmd = [ffmpeg_exe, "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path, "-y"]
        try:
            subprocess.run(audio_cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            return format_tool_result("ERROR", "analyze_video_local", f"Failed to extract audio using ffmpeg: {e.stderr}")
            
        # 2. Extract 3 keyframes (start, middle, end)
        # To do this safely without complex ffprobe logic, we can just extract 3 frames spaced out by using the fps filter
        # e.g., output 3 frames evenly across the whole video. A simpler heuristic is extracting at 10%, 50%, and 90% if we knew duration.
        # Alternatively, we can use a very low framerate like 1 frame per 10 seconds, and pick the first 3. 
        # For simplicity, let's extract exactly 3 frames using the select filter
        frame_pattern = os.path.join(temp_dir, "frame_%d.jpg")
        # Extract 3 frames evenly distributed (roughly)
        frame_cmd = [
            ffmpeg_exe, "-i", video_path, 
            "-vf", "select='eq(n,0)+eq(t,5)+eq(t,10)'", # Rough heuristic: frame 0, 5s, 10s. For robust, we'd calculate duration.
            "-vsync", "vfr", "-frames:v", "3", 
            frame_pattern, "-y"
        ]
        # Let's use a simpler heuristic for now: just grab the first 3 seconds at 1 fps.
        frame_cmd_simple = [
            ffmpeg_exe, "-i", video_path, 
            "-vf", "fps=1", "-frames:v", "3", 
            frame_pattern, "-y"
        ]
        
        try:
            subprocess.run(frame_cmd_simple, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            return format_tool_result("ERROR", "analyze_video_local", f"Failed to extract frames using ffmpeg: {e.stderr}")

        # 3. Transcribe Audio
        transcript = transcribe_audio_local(audio_path)
        if transcript.startswith("ERROR:") or transcript.startswith("WARN:"):
            transcript_out = f"Audio transcription failed or unavailable: {transcript}"
        else:
            transcript_out = f"Audio Transcript:\n{transcript}"

        # 4. Analyze Frames
        b64_images = []
        for i in range(1, 4):
            fpath = os.path.join(temp_dir, f"frame_{i}.jpg")
            if os.path.exists(fpath):
                with open(fpath, "rb") as f:
                    b64_images.append(base64.b64encode(f.read()).decode("utf-8"))
        
        if not b64_images:
            vision_out = "No frames could be extracted for visual analysis."
        else:
            payload = {
                "model": "llava",
                "prompt": "Describe the visual sequence and key events in these sequential video frames.",
                "images": b64_images,
                "stream": False,
                "keep_alive": 0
            }
            req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=json.dumps(payload).encode("utf-8"))
            req.add_header("Content-Type", "application/json")
            
            try:
                with urllib.request.urlopen(req, timeout=120) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    vision_out = f"Visual Description:\n{data.get('response', '')}"
            except Exception as e:
                vision_out = f"Visual analysis failed: {e}"

        # 5. Combine and return
        return f"--- Video Analysis ---\n\n{transcript_out}\n\n{vision_out}\n----------------------"


MULTIMODAL_TOOLS: dict[str, dict[str, Any]] = {
    "analyze_image_local": {
        "func": analyze_image_local,
        "description": inspect.getdoc(analyze_image_local),
    },
    "transcribe_audio_local": {
        "func": transcribe_audio_local,
        "description": inspect.getdoc(transcribe_audio_local),
    },
    "analyze_video_local": {
        "func": analyze_video_local,
        "description": inspect.getdoc(analyze_video_local),
    }
}
