# Learn Mode (Aquila 3.5)

Learn Mode is a **dual-track workspace** inside each agent instance:

| Track | Purpose |
|-------|---------|
| **Classroom** | Canvas-style courses: syllabus ledger, mastery tiers 0–5, Socratic tutor, tier assessments |
| **Archives** | NotebookLM-style source libraries: upload, semantic index, grounded chat, quiz/study exports |

## Storage layout

```
Agent-Instances/{instance_id}/learn/
  courses/{course_id}/
    course.json
    syllabus.json          # canonical ledger (outline + mastery + assessments)
    sources/
    assessments/{id}.json
    tutor_history.json
  archives/{archive_id}/
    archive.json
    sources/
    outputs/               # generated quiz_*.md, study_guide_*.md
    chat_history.json
```

Ephemeral build tasks: `Agent-Tasks/syllabus_build_{course_id}.json` during ingest only.

## Syllabus ledger (`syllabus.json`)

- `nodes[]`: units with `mastery_tier` (0–5), `parent_id`, `required_assessment_id`
- `assessments[]`: specs keyed by id
- `status`: `building` | `active` | `complete`
- **Tier advance (MVP):** pass assessment for node at tier T → `mastery_tier = min(T+1, 5)`; child nodes unlock when parent tier ≥ `tier_gate`
- **Build quality gate:** at least **8 nodes** and **5 sub-units** (`parent_id` set); shallow 3-node outlines are rejected by the `cap.learn.write_syllabus@v1` handler (internal helper: `write_syllabus_file`)

## Intake paths (course create)

1. **Files** — attachments ingested via `cap.learn.ingest_course_materials@v1`, syllabus synthesized
2. **Topic + web** — optional 4-step plan: search → read → synthesize → finalize (`cap.learn.*`)
3. **Placement** — MVP infers weak areas from topic text (no full adaptive diagnostic UI yet)

## Agent runtimes

| Mode | Use |
|------|-----|
| `learn_syllabus_build` | Build `syllabus.json` via `cap.learn.write_syllabus@v1` + `cap.learn.finalize_course@v1` |
| `learn_tutor` | Socratic chat (`AQUILA_LEARN_TUTOR_TEMP`, default 0.7) |
| `learn_archive_chat` | RAG chat with Chroma retrieval (`AQUILA_LEARN_ARCHIVE_TEMP`, default 0.6) |

`learn_syllabus_build` uses the capability act path (`capabilities[]` per turn).

## Archives

- Index: `index_archive_sources` → Chroma collection `learn_archive_{instance}_{id}`; **auto-index on upload** and on archive open when index is stale
- Parsing: uses `file_parser.extract_indexable_text` (same PDF/DOCX path as attachments)
- Chat: top-k chunks injected into `get_learn_archive_prompt`
- Generate: quiz/study markdown written under `outputs/` via GUI subcall + archive generate tools

## Post-MVP (3.5b / 3.6)

- Rich placement diagnostic
- Assignment calendar / due dates
- Writing Mode subcall for polished deliverables
- Slides and images
- Cross-course analytics
