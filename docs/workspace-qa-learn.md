# Learn Mode — QA & bug-hunt checklist

Use this after the **3.5 dual MVP** (Classroom + Archives). Product reference: [learn-mode.md](learn-mode.md).

**Fixes in this pass (verify during QA):**

| Issue | Fix |
|-------|-----|
| Shallow syllabus (3 flat units) | `write_syllabus_file` rejects &lt;8 nodes or &lt;5 `parent_id` sub-units; prompts/planner updated |
| Archive sources not indexed | Auto-index on upload + on open when stale; shared `file_parser.extract_indexable_text` for PDF/DOCX |
| Quiz/study gen empty | Blocked when no indexed chunks; user prompted to re-index |

---

## Prerequisites

- [ ] Ollama reachable; Aquila model loaded
- [ ] `pytest agent/tests/test_learn_*.py -q` passes
- [ ] Learn Mode visible in **Workspace** dropdown (not only on home instance create)
- [ ] Fresh test instance recommended for first full pass

---

## A. Learn home & navigation

| # | Step | Expected |
|---|------|----------|
| A1 | Open Learn Mode | Dual panel: **My courses** / **My archives** |
| A2 | Create instance with `learn` default | Workspace opens on **Learn Mode** |
| A3 | Switch instance | Course/archive lists are per-instance |
| A4 | New course → Back | Returns to home without crash |
| A5 | New archive → Back | Returns to home |

---

## B. Classroom — syllabus build (depth)

| # | Step | Expected |
|---|------|----------|
| B1 | New course, **Files** intake, attach 1+ PDF/MD, build | Build log runs; completes without tool loop error |
| B2 | Inspect `Agent-Instances/{id}/learn/courses/{cid}/syllabus.json` | **≥8** `nodes`, **≥5** with `parent_id`; titles are specific |
| B3 | Syllabus tree in classroom | Multiple modules + sub-units; not 3 generic bullets |
| B4 | Shallow build (if agent tries 3 nodes) | `write_syllabus_file` returns rejection; agent retries deeper tree |
| B5 | **Topic + web** intake + web checkbox | 4-step plan: search → read → synthesize → finalize |
| B6 | **Placement** intake | Build completes; syllabus reflects topic areas |
| B7 | `course.json` | `build_complete: true`; syllabus `status: active` |
| B8 | Course `sources/` | Uploaded files copied; optional course index after build |

**Regression:** Character / Chat modes unchanged.

---

## C. Classroom — tutor & mastery

| # | Step | Expected |
|---|------|----------|
| C1 | Select unit in tree | Assessment panel shows unit + tier |
| C2 | Tutor: ask a concept question | Socratic reply (questions, not full answer dump) |
| C3 | Tutor with course sources indexed | Retrieved chunks may appear in behavior (grounded tone) |
| C4 | Generate assessment (AI) | Questions appear in Assessment tab |
| C5 | Submit score ≥ passing | Tier increases on node; tree badge updates |
| C6 | Submit score below passing | No tier bump; clear message |
| C7 | Locked child (parent tier low) | 🔒 shown until parent gate met |
| C8 | Reload course | `tutor_history.json` persists |

---

## D. Archives — indexing (critical)

| # | Step | Expected |
|---|------|----------|
| D1 | New archive, upload `.md` or `.txt` | File in source list; **auto-index** runs (no manual Re-index required) |
| D2 | Upload PDF with text layer | Index message: N files, M chunks (M &gt; 0) |
| D3 | `archive.json` after index | `index_ready: true`, `chunk_count` &gt; 0 |
| D4 | Open archive with files but stale index | Background re-index if `chunk_count == 0` |
| D5 | Re-index button | Rebuilds collection; stats update |
| D6 | Scan-only PDF (no text) | Warning: 0 chunks; message names file / parser issue |
| D7 | Archive chat: ask fact from source | Answer cites source; admits gap if not in text |

---

## E. Archives — generate & export

| # | Step | Expected |
|---|------|----------|
| E1 | Generate quiz **without** index | Warning dialog; no empty file |
| E2 | Generate quiz **with** index | `outputs/quiz_*.md` created with real content |
| E3 | Generate study doc | `outputs/study_guide_*.md` created |
| E4 | Archive chat after generate | Still grounded; no tool JSON in UI |

---

## F. Agent & data safety

| # | Check |
|---|--------|
| F1 | Syllabus build only writes under `.../learn/courses/{id}/` |
| F2 | Tutor/archive chat: no `MODES_ROSTER`, no raw tool JSON in rail |
| F3 | Ephemeral task: `Agent-Tasks/syllabus_build_*.json` removed or stale cleared on rebuild |
| F4 | No writes to `Agent-Tasks/` from archive chat |

---

## G. Automated tests

```bash
cd agent
python -m pytest tests/test_learn_registry.py tests/test_learn_syllabus_plan.py \
  tests/test_learn_prompts.py tests/test_learn_syllabus_structure.py tests/test_gui_modes.py -q
```

- [ ] All green
- [ ] Full suite: `python -m pytest tests -q` (optional before release)

---

## H. Known limitations (not bugs for this pass)

- Placement intake does not run a full in-GUI diagnostic quiz
- No assignment calendar / due dates
- Quiz/study use one-shot subcall, not Writing Mode polish
- Very large archives may block UI during first index (background worker on open only)

---

## Bug log template

| Date | Area | Steps | Expected | Actual | Severity |
|------|------|-------|----------|--------|----------|
| | Classroom / Archive / GUI | | | | |

---

## Sign-off

| Role | Name | Date | Notes |
|------|------|------|-------|
| Dev smoke | | | B1–D7 |
| User acceptance | | | Full A–F |
