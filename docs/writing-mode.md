# Writing mode (capability-act)

Writing mode uses the same capability-act contract as research, character, and learn: each act turn emits flat `capabilities[]` (not `tools[]`).

## Compose workspace

The **Compose** screen is the primary entry point (Character/Learn-style build flow):

- **Description** — what to write or revise
- **Scope preset** — Quick edit | Short note | Document | Source summary
- **Tone** — neutral, formal, conversational, technical, or custom
- **Length** — target words, paragraphs, section count, or flexible
- **Target document** — optional existing file in Agent-Drafts for revisions
- **Attachments** — built-in attach row with context pane
- **Start writing** — runs the agent with a persisted `writing_brief`

Settings are saved per instance in `Agent-Instances/<id>/writing_defaults.json`.

The **Library** view lists compiled drafts and offers an optional quick AgentRail prompt.

## Writing brief

Stored on the task plan as `plan["writing_brief"]` and drives planning, milestones, and advance policy:

| Field | Purpose |
|-------|---------|
| `scope` | `quick_edit`, `short_form`, `standard`, `from_sources` |
| `tone` / `tone_custom` | Voice for drafts |
| `length_mode` + targets | Words, paragraphs, or sections |
| `advance_when` | `single_draft` (one pass) vs `scope_met` (stay until targets met) |
| `has_attachments` | Enables 3-step read → draft → finalize plans |

## Pipeline

| Step kind | Capability | Purpose |
|-----------|------------|---------|
| `read` | `cap.writing.ingest_sources@v1` | Ingest attachments (source summary / attached files) |
| `write` / `work` | `cap.writing.init_document@v1` | Start draft buffer (only if none exists) |
| `write` / `work` | `cap.writing.draft_sections@v1` | Append grouped sections |
| `write` / `work` | `cap.writing.read_outline@v1` | Optional outline read |
| `finalize` | `cap.writing.finalize_deliverable@v1` | Compile `Agent-Drafts/*.md` and clear active draft |

Dynamic-loop plans are typically two steps: **draft** → **finalize**. With attachments or `from_sources` scope: **read** → **draft** → **finalize**.

## Advance rules

- **Quick edit / short note** (`advance_when: single_draft`): work step advances after one successful `draft_sections` call.
- **Document / source summary** (`advance_when: scope_met`): work step stays open until section/word targets in the brief are met.
- **Init alone never advances** and does not satisfy the draft milestone (only real `draft_sections` calls count).

## Source attachments

1. On Compose (or Library/canvas rails), use **Attach sources** for PDFs, markdown, text, etc.
2. Choose **Source summary** scope or attach files on any scope; the planner adds a read step when needed.
3. Draft steps use scratchpad content from ingest.

## Recipes

- `fn.writing.full_pipeline` — init → draft → compile/finalize
- `fn.writing.dynamic_work` — draft → finalize (default for dynamic loop)
- `fn.writing.dynamic_work_with_sources` — read → draft → finalize

## Artifacts

- Active draft: `Agent-Drafts/active_draft_state.json`
- Compiled deliverable: `Agent-Drafts/<file_name>.md`
- Task summary: `Agent-Creations/<task>.md` — pointer + excerpt linking to the compiled draft (not a stub)
- **Dual-plane plans** (non-micro): `implementation_plan.md` (design + checklist) beside `plan.md` (OS ledger). Tick items with `cap.plan.update_checklist@v1`.

Compile emits `# Title` once and `## Section` per section. `write_section` / compile strip duplicate leading `#` titles from section bodies and markdown hashes from headers so deliverables do not show stacked headings.

## Harness

Scenario `writing_short` in the capability harness expects capability-first objectives and accepts `cap.writing.finalize_deliverable@v1` as a finalize signal.

## Tests

```bash
python -m pytest agent/tests/test_writing_brief.py agent/tests/test_writing_capability_parity.py agent/tests/test_step_policies.py agent/tests/test_loop_objectives.py agent/tests/test_plan_artifact.py -q
```
