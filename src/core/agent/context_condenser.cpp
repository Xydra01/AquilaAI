#include "aquila/agent/context_condenser.hpp"

#include "aquila/modules/module.hpp"  // estimate_tokens (D:L190-192)

namespace aquila {

ContextCondenser::ContextCondenser(TierLimits limits) : limits_(limits) {}

void ContextCondenser::set_pinned_prefix(std::string system_prompt, std::string recipe_schema) {
    system_prompt_ = std::move(system_prompt);
    recipe_schema_ = std::move(recipe_schema);
}

void ContextCondenser::set_anchored(
    const AgentScratchpad& scratchpad,
    const std::vector<std::pair<std::string, Json>>& module_snapshots) {
    // Retain the raw inputs so condense() can refresh the anchored block from the
    // most recent set_anchored() inputs without the caller re-supplying them (Req 2.4).
    anchored_scratchpad_ = scratchpad;
    anchored_snapshots_ = module_snapshots;
    render_anchored();
}

void ContextCondenser::render_anchored() {
    // Render the cached scratchpad + module snapshots into a single stable system
    // message. The anchored block is one `system` message (design "Condenser
    // internals"); condense() re-runs this same rendering so the refreshed block is
    // byte-identical to the latest set_anchored() output (Req 2.4).
    Json rendered = Json::object();
    to_json(rendered["scratchpad"], anchored_scratchpad_);
    Json snapshots = Json::object();
    for (const auto& [id, snap] : anchored_snapshots_) {
        snapshots[id] = snap;
    }
    rendered["module_snapshots"] = std::move(snapshots);

    anchored_.role = Role::system;
    anchored_.content = rendered.dump();
    anchored_.images.clear();
}

std::vector<Message> ContextCondenser::build_messages() const {
    std::vector<Message> messages;

    // 1. Pinned prefix [0..P]: system prompt message, then recipe schema message.
    messages.push_back(Message{Role::system, system_prompt_, {}});
    messages.push_back(Message{Role::system, recipe_schema_, {}});

    // 2. Anchored block [P+1..S]: one system message with the scratchpad + snapshots.
    messages.push_back(anchored_);

    // 3. Rolling tail [S+1..end]: each recorded interaction becomes a user/tool
    //    message pair, emitted in recorded order (oldest first).
    for (const ToolInteraction& interaction : tail_) {
        Json call = Json::object();
        call["module"] = interaction.module;
        call["action"] = interaction.action;
        call["args"] = interaction.args;
        messages.push_back(Message{Role::user, call.dump(), {}});
        messages.push_back(Message{Role::tool, interaction.result.llm_facing_output, {}});
    }

    // Pending corrective/guidance messages trail the tool cycles as user messages.
    for (const std::string& text : guidance_) {
        messages.push_back(Message{Role::user, text, {}});
    }

    return messages;
}

const std::string* ContextCondenser::resolve_spill(const std::string& ref) const {
    if (const auto it = spill_.find(ref); it != spill_.end()) {
        return &it->second;
    }
    return nullptr;
}

// --- Methods owned by task 4.2 (ring buffer + head+tail spill) ---------------

namespace {

// Back off a byte index so it never lands in the middle of a UTF-8 sequence.
// Continuation bytes are 10xxxxxx (0x80..0xBF); a cut is legal only at a lead
// byte or at end-of-string. The budget stays a byte budget (matching the rest
// of the project, e.g. exec/diagnostics.cpp); this only avoids emitting a
// mangled code unit. Backs off at most 3 bytes (max UTF-8 sequence length).
std::size_t back_off_to_utf8_boundary(const std::string& text, std::size_t index) {
    if (index >= text.size()) return text.size();
    const auto is_continuation = [&](std::size_t i) {
        return (static_cast<unsigned char>(text[i]) & 0xC0U) == 0x80U;
    };
    while (index > 0 && is_continuation(index)) {
        --index;
    }
    return index;
}

// Advance a byte index forward to the next UTF-8 lead byte (or end-of-string)
// so a tail slice starts on a clean boundary.
std::size_t forward_to_utf8_boundary(const std::string& text, std::size_t index) {
    const auto is_continuation = [&](std::size_t i) {
        return (static_cast<unsigned char>(text[i]) & 0xC0U) == 0x80U;
    };
    while (index < text.size() && is_continuation(index)) {
        ++index;
    }
    return index;
}

}  // namespace

void ContextCondenser::record_tool_cycle(const ToolInteraction& interaction) {
    // Head+tail-truncate the LLM-facing output before it enters the tail; the full
    // text (if oversized) lands in spill_ keyed by the ref embedded in the view.
    ToolInteraction stored = interaction;
    std::string ref;
    stored.result.llm_facing_output =
        head_tail_truncate(interaction.result.llm_facing_output, ref);

    // Ring buffer, cap K = limits_.rolling_tools (Req 2.2): drop the oldest entries
    // so that after push_back the tail holds exactly the last min(M, K) in order and
    // never exceeds K. If K == 0 the tail stays empty (no underflow).
    const std::size_t k = limits_.rolling_tools;
    if (k == 0) {
        return;
    }
    while (tail_.size() >= k) {
        tail_.pop_front();
    }
    tail_.push_back(std::move(stored));
}

void ContextCondenser::push_guidance(std::string text) {
    guidance_.push_back(std::move(text));
}

std::string ContextCondenser::head_tail_truncate(const std::string& text, std::string& out_ref) {
    // Shorter outputs are stored verbatim with no spill (Req 2.3).
    if (text.size() <= limits_.tool_output_chars) {
        out_ref.clear();
        return text;
    }

    // Mint a stable, unique reference and spill the full text so resolve_spill(ref)
    // can recover it later (R8).
    const std::string ref = "spill:" + std::to_string(spill_seq_++);
    spill_[ref] = text;
    out_ref = ref;

    // Split a budget of tool_output_chars bytes into a head and a tail slice joined
    // by a marker embedding the ref, e.g. "... [spilled N chars, ref=spill:7] ...".
    // Keeping the tail preserves the end of a diagnostic, where the error summary
    // usually lives (R19; diverges from Python's head-only truncate_text).
    const std::size_t budget = limits_.tool_output_chars;
    const std::size_t head_budget = budget / 2;
    const std::size_t tail_budget = budget - head_budget;

    const std::size_t head_end = back_off_to_utf8_boundary(text, head_budget);
    const std::size_t tail_start =
        forward_to_utf8_boundary(text, text.size() - tail_budget);
    const std::size_t elided = tail_start - head_end;

    std::string view;
    view.reserve(head_end + tail_budget + 48);
    view.append(text, 0, head_end);
    view += "... [spilled ";
    view += std::to_string(elided);
    view += " chars, ref=";
    view += ref;
    view += "] ...";
    view.append(text, tail_start, text.size() - tail_start);
    return view;
}

// --- Methods owned by task 4.3 (token estimation + condense threshold + wipe) -

std::uint64_t ContextCondenser::estimate_prompt_tokens() const {
    std::uint64_t total = 0;
    for (const Message& message : build_messages()) {
        total += estimate_tokens(message.content);
    }
    return total;
}

bool ContextCondenser::should_condense() const {
    return estimate_prompt_tokens() >= limits_.condense_threshold;
}

void ContextCondenser::condense() {
    // Wipe policy (Req 2.4): the pinned prefix (system_prompt_ / recipe_schema_) is
    // never touched; the anchored block is refreshed from the most recent
    // set_anchored() inputs via the shared renderer so it equals that rendering; the
    // rolling tail and any pending guidance are cleared.
    render_anchored();
    tail_.clear();
    guidance_.clear();
}

}  // namespace aquila
