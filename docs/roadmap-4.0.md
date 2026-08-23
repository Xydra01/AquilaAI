# Aquila OS 4.0 — Roadmap (draft)

**Status:** Planning only — do not implement until 3.5 QA is complete and this doc is reviewed.

4.0 is the release where Aquila becomes a **headless-capable, voice-operable, locally-hosted agent platform** — not only a desktop GUI for power users. It builds on 3.5 (Learn, MCP, Remote Companion, dynamic loop) and the experimental ML work started in Data Processing mode and `agent/vision/`.

---

## North star

Long-term: integrate Aquila into **open-source home server / smart-home stacks** as a **local reasoning and automation brain**. That hardware and integration work is **vision-only for now** — see [smart-home-vision.md](smart-home-vision.md). No Home Assistant / MQTT / webhook **code** in 4.0.

Near-term 4.0 delivers:

- Operated by **voice** (wake phrase + toggle, or push-to-talk fallback)
- Fed **multimodal context** via lightweight on-device models (perception layer)
- **ML Lab** — plan-driven ML workflows (train → evaluate → deploy → run inference)
- **Productivity workspaces** — **Lifestyle** (calendar/planning), **Communication** (email inbox), and a **Workflow editor** on top of orchestration
- **Prompt suggestion** on typing surfaces (cross-cutting UX, SML-backed)

The GUI and Remote Companion remain first-class; voice and optional ML install as **peer capabilities** on the same agent core.

---

## Decisions (locked for planning)

| Topic | Decision |
|-------|----------|
| **Wake word** | Ship from voice MVP day one. Phrases: **“Aquila”**, **“Hey Aquila”**, and close variants. **Must be a user toggle** (Settings / `.env`) so development, demos, and conversation *about* Aquila do not trigger accidental activation. Push-to-talk remains a fallback when wake is off. |
| **ML mode name** | **ML Lab** (replaces “Data Processing” / “ML Workbench” in user-facing 4.0 UI). |
| **Packaging** | **Optional pip extras** — core Aquila does not require `torch`, STT, or TTS. Full-featured optional installs: `aquila[ml]`, `aquila[voice]`. Each extra is a self-contained capability layer, not a stub. |
| **Smart home** | **Document vision only** in 4.0 — no HA/MQTT/webhook implementation until hardware and requirements settle (~1+ year). See [smart-home-vision.md](smart-home-vision.md). |
| **Social / chat apps** | Discord, Instagram, Messenger, etc. — **not 4.0**; email-first in [communication-vision.md](communication-vision.md). |
| **Email autonomous send** | Draft-first in 4.0; unattended send only with explicit opt-in rules (see Communication vision). |
| **Calendar sync** | ICS import in Lifestyle MVP; CalDAV / Google OAuth in 4.x — see [lifestyle-vision.md](lifestyle-vision.md). |

### Still open

- **ML backends:** PyTorch-first (ResNet path) vs later ONNX/TFLite export — decide during ML Lab implementation.
- **Pseudo-labeling, labeling UI, Learn + ML Lab crossover** — see [ml-lab-vision.md](ml-lab-vision.md).
- **`aquila[comms]` extra** — whether IMAP/OAuth deps ship as optional extra vs core (lean toward optional).
- **Learn due dates vs Lifestyle** — merged calendar feed vs separate views.

---

## Pillars

| Pillar | Summary | Builds on |
|--------|---------|-----------|
| **A. Voice interface** | Wake phrase + toggle, STT/TTS, headless service | Remote Companion, generation lock |
| **B. ML Lab** | Data Processing → plan-driven ML workflows | `agent/tasks/data_processor.py`, `agent/vision/` |
| **C. Perception layer** | Lightweight CNNs / classifiers before LLM reasoning | `cnn_classifier.py`, attachments |
| **D. Orchestration + Workflow editor** | Task delegation stack, artifact handoff, **saved visual workflows** | `delegate_mode`, `ModeRunner`, [workflow-editor-vision.md](workflow-editor-vision.md) |
| **E. Platform hygiene** | Stable imports; optional extras in `requirements.txt` | `agent/__init__.py` shims |
| **F. Lifestyle workspace** | Calendar, planning, ICS import (CalDAV/OAuth later) | `calendar_tools.py`, Learn due dates |
| **G. Communication workspace** | Smart inbox, draft assist, guarded send | `email_tools.py`, Settings SMTP |
| **— Cross-cutting** | **Prompt suggestion** on all prompt surfaces | `aquila-lite` / SML, [prompt-suggestion-vision.md](prompt-suggestion-vision.md) |

**5.0** remains **multi-worker parallelism** — not part of 4.0.

---

## Pillar A — Voice (flagship)

See **[voice-interface-vision.md](voice-interface-vision.md)**.

**Minimum viable 4.0 voice (requires `aquila[voice]`):**

1. **Wake phrase** (“Aquila”, “Hey Aquila”, …) with **off-by-default or easy-off toggle**
2. **Push-to-talk** when wake is disabled
3. Local **STT** → intent routing → same modes as today
4. Local **TTS** for replies and task status
5. Spoken **cancel / status / read summary**
6. Voice service runs without GUI; optional GUI indicator when wake is listening

---

## Pillar B — ML Lab

See **[ml-lab-vision.md](ml-lab-vision.md)**.

**Origin:** Data Processing mode was a rush internship helper — **disabled** until ML Lab ships (`AQUILA_ENABLE_DATA_PROCESSING=0` today).

**4.0:** **ML Lab** workspace (requires `aquila[ml]`) — ledger-backed ingest → plan → train → evaluate → deploy → operate.

---

## Pillar C — Perception layer

Lightweight models produce **structured facts** for the LLM. Shipped with `aquila[ml]` or shared perception subset TBD.

| Modality | Model class | Aquila use |
|----------|-------------|------------|
| **Images** | ResNet/MobileNet-style CNNs | Attachment tagging, batch labels |
| **Audio** | CNN classification; Whisper for transcription | Events vs voice commands |
| **Tabular** | Small nets / classical ML | Column typing, anomalies |

---

## Pillar D — Orchestration + Workflow editor

See **[workflow-editor-vision.md](workflow-editor-vision.md)** and [loop-rework-and-parallelism.md](loop-rework-and-parallelism.md).

- Task workspace **mode stack** UI
- Scratchpad / artifact handoff across delegations
- **Workflow editor** — block-style graph: modes, per-node prompts, handoff edges, save/reuse
- **ML Lab** as delegation target (“delegate to ml_lab with dataset X”)
- Saved workflows under `Agent-Instances/{id}/workflows/`; compile to Autonomous Task runs

---

## Pillar F — Lifestyle workspace

See **[lifestyle-vision.md](lifestyle-vision.md)**.

- New major sidebar: **Lifestyle** (calendar + planning)
- **4.0e MVP:** local calendar DB, **ICS import** (export from Apple/Google), agenda UI, calendar tools in Chat/Voice
- **4.x:** CalDAV read-only sync, optional Google OAuth
- Integrate Learn assignment due dates (avoid duplicate calendar UIs)

---

## Pillar G — Communication workspace

See **[communication-vision.md](communication-vision.md)**.

- New major sidebar: **Communication** (email-first smart inbox)
- **4.0f MVP:** IMAP read, thread UI, Aquila **draft assist**, user-confirmed send via existing SMTP
- Autonomous send: **opt-in rules only**, off by default
- **Not 4.0:** Discord, Instagram, Messenger (4.x+ connectors)

---

## Cross-cutting — Prompt suggestion

See **[prompt-suggestion-vision.md](prompt-suggestion-vision.md)**.

- **Suggest** control on prompt/typing surfaces (Chat, Task, …)
- Rewrites user text via fast local model (`aquila-lite` or `AQUILA_SUGGEST_MODEL`)
- Preview → Accept / Edit / Dismiss; does not auto-submit
- Can ship early (**4.0-cross**) alongside 4.0a

---

## Pillar E — Platform hygiene & packaging

```text
pip install aquila              # core: GUI, loop, Ollama, research, code, Lifestyle shell, …
pip install aquila[voice]       # STT, TTS, wake-word service deps
pip install aquila[ml]          # torch, ML Lab, perception tools, train/infer
pip install aquila[comms]       # (proposed) IMAP/OAuth helpers for Communication workspace
pip install aquila[voice,ml]    # full local multimodal stack
```

- Core install must not import `torch` at startup.
- ML Lab and Voice pages hidden unless extra installed (and feature flags as needed).
- Document extras in README and Settings (“install voice support”).

---

## Proposed phasing

| Phase | Focus | User-visible outcome |
|-------|--------|----------------------|
| **4.0-cross** | Prompt suggestion | Suggest button on Chat + Task inputs |
| **4.0a** | Orchestration + **Workflow editor** MVP | Delegation stack + save/run workflows |
| **4.0b** | ML Lab MVP (`aquila[ml]`) | Train → evaluate → deploy; replaces Data Processing |
| **4.0c** | Perception tools | `classify_image` in chat/task |
| **4.0d** | Voice MVP (`aquila[voice]`) | Wake phrase + toggle, PTT, STT/TTS service |
| **4.0e** | Lifestyle MVP | Calendar UI + ICS import + planning tools |
| **4.0f** | Communication MVP (`aquila[comms]` TBD) | Inbox + draft assist + confirm-to-send |
| **4.0-doc** | Smart home vision | [smart-home-vision.md](smart-home-vision.md) only — **no integration code** |

**Suggested build order:** 4.0a (+ cross) → 4.0b/c → 4.0d (headline) → 4.0e/f (productivity workspaces). Lifestyle and Communication can swap if email is higher priority.

Voice remains the marketing headline; orchestration + ML Lab are the agent-engineering foundation; Lifestyle / Communication expand daily-use GUI without replacing existing modes.

---

## Relationship to 3.5 experiments

| 3.5 artifact | 4.0 role |
|--------------|----------|
| Data Processing mode | Prototype → **ML Lab**; stay disabled until 4.0b |
| `agent/vision/` | ML Lab library |
| `calendar_tools.py` | Foundation for **Lifestyle** (ICS import exists) |
| `email_tools.py` + Settings Email | Outbound only → **Communication** adds inbox + GUI |
| `standalone_cnn_toolkit/` | Local-only; not in pip package |
| Remote Companion | Voice + workflow run transport pattern |

---

## Non-goals for 4.0

- Home Assistant / MQTT / webhook **implementation** (vision doc only)
- **Discord / Instagram / Messenger** integrations (4.x+)
- Multi-GPU parallel mode loops (**5.0**)
- Cloud model marketplace
- Shipping large weights in Git
- Full two-way Google/Apple calendar sync in MVP (ICS import is enough for 4.0e)

---

## Planning notes (productivity features — March 2026)

| Idea | Alignment | Recommendation |
|------|-----------|----------------|
| **Workflow editor** | Extends Pillar D; same runtime as Task delegation | **4.0a** — ship with orchestration, not after |
| **Prompt suggestion** | Independent; uses lite model | **4.0-cross** — early win, low conflict with voice/ML |
| **Lifestyle** | New pillar; `calendar_tools.py` already started | **4.0e** — ICS first; CalDAV/OAuth in 4.x |
| **Communication** | New pillar; SMTP exists, need IMAP + UI | **4.0f** — draft-first; defer social apps |
| **Autonomous email send** | High trust/risk | Opt-in rules only; default **draft + confirm** |

---

## References

- [roadmap-3.5.md](roadmap-3.5.md)
- [ml-lab-vision.md](ml-lab-vision.md)
- [voice-interface-vision.md](voice-interface-vision.md)
- [smart-home-vision.md](smart-home-vision.md)
- [workflow-editor-vision.md](workflow-editor-vision.md)
- [lifestyle-vision.md](lifestyle-vision.md)
- [communication-vision.md](communication-vision.md)
- [prompt-suggestion-vision.md](prompt-suggestion-vision.md)
- [data-processing-mode.md](data-processing-mode.md) — 3.5 prototype (superseded by ML Lab)
- [vision-and-cnn.md](vision-and-cnn.md)
- [loop-rework-and-parallelism.md](loop-rework-and-parallelism.md)
- [remote-companion.md](remote-companion.md)
