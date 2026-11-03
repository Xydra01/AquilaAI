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
    "fn.persona.build": Recipe(
        recipe_id="fn.persona.build",
        title="Persona build",
        description="Ingest → write initialization → finalize.",
        capability_ids=(
            "cap.persona.ingest_sources@v1",
            "cap.persona.write_initialization@v1",
            "cap.persona.finalize@v1",
        ),
    ),
    "fn.persona.build_with_lore": Recipe(
        recipe_id="fn.persona.build_with_lore",
        title="Persona build with lore",
        description="Gather lore → ingest → write initialization → finalize.",
        capability_ids=(
            "cap.persona.gather_lore@v1",
            "cap.persona.ingest_sources@v1",
            "cap.persona.write_initialization@v1",
            "cap.persona.finalize@v1",
        ),
    ),
    "fn.learn.syllabus": Recipe(
        recipe_id="fn.learn.syllabus",
        title="Syllabus build",
        description="Ingest materials → write syllabus → finalize course.",
        capability_ids=(
            "cap.learn.ingest_course_materials@v1",
            "cap.learn.write_syllabus@v1",
            "cap.learn.finalize_course@v1",
        ),
    ),
    "fn.learn.syllabus_web": Recipe(
        recipe_id="fn.learn.syllabus_web",
        title="Syllabus build with web",
        description="Gather topic sources → ingest → write syllabus → finalize.",
        capability_ids=(
            "cap.learn.gather_topic_sources@v1",
            "cap.learn.ingest_course_materials@v1",
            "cap.learn.write_syllabus@v1",
            "cap.learn.finalize_course@v1",
        ),
    ),
    "fn.writing.full_pipeline": Recipe(
        recipe_id="fn.writing.full_pipeline",
        title="Full writing pipeline",
        description="Init document → draft sections → compile/finalize.",
        capability_ids=(
            "cap.writing.init_document@v1",
            "cap.writing.draft_sections@v1",
            "cap.writing.compile_document@v1",
            "cap.writing.finalize_deliverable@v1",
        ),
    ),
    "fn.writing.dynamic_work": Recipe(
        recipe_id="fn.writing.dynamic_work",
        title="Dynamic writing work",
        description="Draft sections then finalize deliverable.",
        capability_ids=(
            "cap.writing.draft_sections@v1",
            "cap.writing.finalize_deliverable@v1",
        ),
    ),
    "fn.writing.dynamic_work_with_sources": Recipe(
        recipe_id="fn.writing.dynamic_work_with_sources",
        title="Writing with source attachments",
        description="Ingest attachments → draft from sources → finalize.",
        capability_ids=(
            "cap.writing.ingest_sources@v1",
            "cap.writing.draft_sections@v1",
            "cap.writing.finalize_deliverable@v1",
        ),
    ),
    "fn.dev.implement": Recipe(
        recipe_id="fn.dev.implement",
        title="Code implement",
        description="Recon → edit → sync project.",
        capability_ids=(
            "cap.dev.recon@v1",
            "cap.dev.edit_apply@v1",
            "cap.dev.sync_project@v1",
        ),
    ),
    "fn.dev.documentation": Recipe(
        recipe_id="fn.dev.documentation",
        title="Code documentation",
        description="Recon → read → write docs → sync.",
        capability_ids=(
            "cap.dev.recon@v1",
            "cap.dev.read_region@v1",
            "cap.dev.write_docs@v1",
            "cap.dev.sync_project@v1",
        ),
    ),
    "fn.dev.tdd": Recipe(
        recipe_id="fn.dev.tdd",
        title="Code TDD",
        description="Recon → create failing test → implement → verify → sync.",
        capability_ids=(
            "cap.dev.recon@v1",
            "cap.dev.create_file@v1",
            "cap.dev.edit_apply@v1",
            "cap.dev.run_tests@v1",
            "cap.dev.sync_project@v1",
        ),
    ),
    "fn.dev.dynamic_work": Recipe(
        recipe_id="fn.dev.dynamic_work",
        title="Dynamic code work",
        description="Edit/work then sync on finalize.",
        capability_ids=(
            "cap.dev.edit_apply@v1",
            "cap.dev.sync_project@v1",
        ),
    ),
}


def get_recipe(recipe_id: str) -> Recipe | None:
    return RECIPE_REGISTRY.get(recipe_id)
