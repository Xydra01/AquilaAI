"""Read web pages capability."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability
from agent.research import register_read_webpage_source
from agent.tool_library.web_tools import read_webpage


class ReadPagesInput(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=8)
    max_chars: int | None = Field(None, ge=1000)


class ReadPagesOutput(BaseModel):
    pages: list[dict] = Field(default_factory=list)


def _run_read_pages(ctx: CapabilityContext, inp: ReadPagesInput) -> CapabilityResult:
    if ctx.offline:
        return CapabilityResult.failure("offline", "Web read unavailable in offline mode.")
    if ctx.cancel_check and ctx.cancel_check():
        return CapabilityResult.failure("cancelled", "Run cancelled.")

    pages: list[dict] = []
    for url in inp.urls[:8]:
        url = (url or "").strip()
        if not url:
            continue
        content = read_webpage(url, max_chars=inp.max_chars)
        pages.append({"url": url, "content": content, "ok": not str(content).startswith("❌")})
        if ctx.source_registry is not None:
            register_read_webpage_source(
                ctx.source_registry,
                url,
                content,
                step_index=ctx.step_index,
            )
    ok_count = sum(1 for p in pages if p.get("ok"))
    return CapabilityResult.success(
        f"Read {ok_count}/{len(pages)} pages.",
        pages=pages,
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.web.read_pages@v1",
        version="v1",
        title="Read web pages",
        description="Fetch 1–N URLs with caps and page quality analysis.",
        input_model=ReadPagesInput,
        handler=_run_read_pages,
        tier="A",
    )
)
