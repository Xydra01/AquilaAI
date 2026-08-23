"""Synthesize notes with optional internal LLM compression."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability, run_capability
from agent.tool_library.agent_tools import save_research_note


class SynthesizeNotesInput(BaseModel):
    topic: str = Field("", description="Topic for synthesis header")
    max_input_chars: int = Field(12000, ge=2000)
    use_llm: bool = True
    num_predict: int = Field(1024, ge=256, le=2048)


def _run_synthesize(ctx: CapabilityContext, inp: SynthesizeNotesInput) -> CapabilityResult:
    read_result = run_capability(
        "cap.research.read_notes@v1",
        ctx,
        {"max_chars": inp.max_input_chars, "tail": True},
    )
    if not read_result.ok:
        return read_result
    notes = str(read_result.data.get("text") or "")
    if not notes.strip() or "No research notes found" in notes:
        return CapabilityResult.failure("no_notes", "No research notes to synthesize.")

    topic = (inp.topic or ctx.user_request or "Research synthesis").strip()[:200]
    body = notes

    if inp.use_llm and ctx.client is not None:
        prompt = (
            f"Synthesize the following research notes into a structured summary for: {topic}\n\n"
            "Include key facts, comparisons, and open questions. Use markdown headings.\n\n"
            f"{notes[:inp.max_input_chars]}"
        )
        try:
            result = ctx.client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.4,
                stream=False,
                surface="act",
                num_predict=inp.num_predict,
            )
            if isinstance(result, dict):
                content = result.get("message", {}).get("content", "") or ""
                if content.strip():
                    body = content.strip()
        except Exception:
            pass

    header = f"# Synthesis: {topic}\n\n"
    save_out = save_research_note(header + body, task_name=ctx.task_id or None)
    if str(save_out).startswith("❌"):
        return CapabilityResult.failure("save_failed", save_out)
    return CapabilityResult.success(
        "Synthesis note saved.",
        chars=len(body),
        tool_result=save_out,
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.research.synthesize_notes@v1",
        version="v1",
        title="Synthesize notes",
        description="Read notes, optional LLM compress, append synthesis note.",
        input_model=SynthesizeNotesInput,
        handler=_run_synthesize,
        tier="B",
    )
)
