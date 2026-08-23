"""Recipe registry: intent → ordered capability sequences."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Recipe:
    recipe_id: str
    title: str
    description: str
    capability_ids: tuple[str, ...]


RECIPE_REGISTRY: dict[str, Recipe] = {
    "fn.research.full_pipeline": Recipe(
        recipe_id="fn.research.full_pipeline",
        title="Full research pipeline",
        description="Optional brief → gather → synthesize → compile → finalize.",
        capability_ids=(
            "cap.research.gather_web_sources@v1",
            "cap.research.synthesize_notes@v1",
            "cap.research.compile_report@v1",
            "cap.research.finalize_deliverable@v1",
        ),
    ),
    "fn.research.dynamic_work": Recipe(
        recipe_id="fn.research.dynamic_work",
        title="Dynamic research work",
        description="Gather + synthesize loop until milestones, then compile + finalize.",
        capability_ids=(
            "cap.research.gather_web_sources@v1",
            "cap.research.synthesize_notes@v1",
            "cap.research.compile_report@v1",
            "cap.research.finalize_deliverable@v1",
        ),
    ),
    "fn.research.offline_pipeline": Recipe(
        recipe_id="fn.research.offline_pipeline",
        title="Offline research pipeline",
        description="Ingest offline → synthesize → compile → finalize.",
        capability_ids=(
            "cap.research.ingest_offline@v1",
            "cap.research.synthesize_notes@v1",
            "cap.research.compile_report@v1",
            "cap.research.finalize_deliverable@v1",
        ),
    ),
    "fn.research.chat_light": Recipe(
        recipe_id="fn.research.chat_light",
        title="Light research (chat)",
        description="Light web context for chat injection.",
        capability_ids=(
            "cap.research.light_web_context@v1",
        ),
    ),
}


def get_recipe(recipe_id: str) -> Recipe | None:
    return RECIPE_REGISTRY.get(recipe_id)
