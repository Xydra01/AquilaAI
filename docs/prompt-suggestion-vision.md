# Prompt suggestion vision (Aquila 4.0 — cross-cutting UX)

**Status:** Draft — planning document only.

**Scope:** All **typing / prompt surfaces** — Chat, Character, Learn, Task prompt, Research query, Writing, Code, Communication compose, Workflow node prompts, Remote Companion input.

## Goal

A **Suggest** control (button, chip, or subtle highlight) that rewrites what the user already typed into a **clearer, more actionable prompt** — without replacing the user’s intent.

Uses a **small / fast model (SML)** when possible (e.g. `aquila-lite`) so the main model stays free for heavy work.

## Principles

1. **Non-destructive** — show suggestion in a diff or side-by-side preview; user **Accept**, **Edit**, or **Dismiss**.
2. **Do not hold generation lock** for long — SML rewrite is a short, low-token chat call; timeout aggressively (e.g. 15–30s).
3. **Context-aware when cheap** — include mode name (“Research”, “Code”) and optional one-line system hint; do not attach full codebase by default.
4. **Same privacy** — local Ollama only unless user configured otherwise.
5. **Accessible** — keyboard shortcut (e.g. Ctrl+Space) mirroring the button.

## UX pattern (target)

```
[ User types in input........................ ]
[ ✨ Suggest better prompt ]     [ Send ]
        ↓
┌─ Suggested ─────────────────────────────┐
│ Rewrite: clearer, specific, mode-aware  │
│ [Use this] [Edit] [Dismiss]             │
└─────────────────────────────────────────┘
```

Optional: inline underline on “vague” phrases (stretch — needs lighter heuristics or second pass).

## Implementation notes

| Concern | Approach |
|---------|----------|
| Model | Prefer `aquila-lite` or dedicated env `AQUILA_SUGGEST_MODEL` |
| Prompt template | Fixed system prompt per surface family (chat vs task vs email) |
| Concurrency | Skip if generation lock busy; queue or show “try again” |
| Packaged CPU | Still useful on lite; disable auto-trigger on keypress if too slow |

## MVP checklist (4.0-cross — can land early in 4.0a)

- [ ] Shared `PromptSuggestService` (one API for all pages)
- [ ] Chat + Task inputs wired first
- [ ] Preview + accept flow
- [ ] Settings toggle: `AQUILA_PROMPT_SUGGEST=0|1`, model override
- [ ] Tests with mocked Ollama response

## Stretch

- [ ] Learn, Writing, Code, Communication, Workflow editor nodes
- [ ] Remote Companion PWA suggest button
- [ ] Voice: “rephrase that” on last STT transcript
- [ ] Learn-from-acceptance (local only): optional “remember my style” — privacy review required

## Non-goals (4.0)

- Auto-submitting rewritten prompts without user accept
- Cloud-only rewrite APIs as default
- Full grammar checker product — scope is **prompt quality for Aquila modes**

## See also

- [roadmap-4.0.md](roadmap-4.0.md)
- [hardware-compatibility.md](hardware-compatibility.md) — lite model on CPU
