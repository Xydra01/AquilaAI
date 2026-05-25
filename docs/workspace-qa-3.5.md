# Workspace QA — Aquila 3.5 (Learn mode)

Dual MVP: **Classroom** (courses, syllabus, Socratic tutor, assessments) + **Archives** (sources, index, RAG chat, quiz/study export).

## Prerequisites

- [ ] 3.4 QA complete ([workspace-qa-3.4.md](workspace-qa-3.4.md), [workspace-qa-cai.md](workspace-qa-cai.md))
- [ ] `pytest agent/tests -q` passes on `Aquila-3.5` branch

## Learn home

- [ ] Learn Mode opens dual home (courses + archives), not stub
- [ ] Course and archive lists load per instance
- [ ] Switching instances preserves Learn data per instance
- [ ] New course / new archive flows open create views

## Classroom — syllabus build

- [ ] Create course: files intake builds `syllabus.json` (≥8 nodes, ≥5 sub-units — see [workspace-qa-learn.md](workspace-qa-learn.md))
- [ ] Topic + web intake runs 4-step plan when web enabled
- [ ] Placement intake completes (MVP topic-weighted syllabus)
- [ ] `finalize_course` marks course active; classroom opens

## Classroom — tutor & mastery

- [ ] Syllabus tree shows tier badges; locked children when parent below gate
- [ ] Tutor chat streams; replies are Socratic (questions, no direct answers)
- [ ] Generate assessment → take/submit score → tier increases on pass
- [ ] `tutor_history.json` persists per course

## Archives

- [ ] Upload sources auto-indexes; Re-index still works; see [workspace-qa-learn.md](workspace-qa-learn.md) section D
- [ ] Archive chat cites grounded content after index
- [ ] Generate quiz / study doc writes markdown under `outputs/`

## Agent / data safety

- [ ] Syllabus build writes only under `Agent-Instances/.../learn/courses/`
- [ ] No `MODES_ROSTER` or tool JSON in tutor/archive chat
- [ ] Character AI, Chat, Research, Writing, Code, Task workspaces unchanged

## Automated

- [ ] `pytest agent/tests/test_learn_*.py -q` passes
- [ ] `pytest agent/tests -q` passes (full suite)
