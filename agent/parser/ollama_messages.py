"""Convert OpenAI-style chat messages to native Ollama /api/chat shape."""
from __future__ import annotations

from typing import Any


def _strip_data_url(url: str) -> str:
    text = (url or "").strip()
    if "," in text and text.lower().startswith("data:"):
        return text.split(",", 1)[1]
    return text


def adapt_messages_openai_to_native(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Map Aquila/OpenAI multimodal messages to Ollama native chat messages.

    OpenAI-style user content:
      [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "data:..."}}]

    Native:
      {"role": "user", "content": "...", "images": ["base64..."]}
    """
    out: list[dict[str, Any]] = []
    for msg in messages or []:
        role = str(msg.get("role", "user"))
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts: list[str] = []
            images: list[str] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type", "")
                if ptype == "text":
                    text_parts.append(str(part.get("text", "") or ""))
                elif ptype == "image_url":
                    iu = part.get("image_url") or {}
                    url = iu.get("url", "") if isinstance(iu, dict) else str(iu)
                    b64 = _strip_data_url(str(url))
                    if b64:
                        images.append(b64)
            native: dict[str, Any] = {
                "role": role,
                "content": "".join(text_parts) if text_parts else "",
            }
            if images:
                native["images"] = images
            out.append(native)
        else:
            native: dict[str, Any] = {"role": role, "content": str(content or "")}
            if "images" in msg:
                native["images"] = msg["images"]
            out.append(native)
    return out
