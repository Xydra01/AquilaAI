#include "aquila/agent/context_condenser.hpp"

#include "aquila/modules/module.hpp"  // estimate_tokens (D:L190-192)

namespace aquila {

ContextCondenser::ContextCondenser(TierLimits limits, CondenserStrategy strategy)
    : limits_(limits), strategy_(strategy) {}

void ContextCondenser::set_pinned_prefix(std::string system_prompt, std::string recipe_schema) {
    system_prompt_ = std::move(system_prompt);
    recipe_schema_ = std::move(recipe_schema);
}

void ContextCondenser::set_anchored(
    const AgentScratchpad& scratchpad,
    const std::vector<std::pair<std::string, Json>>& module_snapshots,
    const TaskLedger* ledger) {
    // Retain the raw inputs so condense() can refresh the anchored block from the
    // most recent set_anchored() inputs without the caller re-supplying them (Req 2.4).
    anchored_scratchpad_ = scratchpad;
    anchored_snapshots_ = module_snapshots;
    if (ledger != nullptr) {
        anchored_ledger_ = *ledger;
    } else {
        anchored_ledger_.reset();
    }
    render_anchored();
}

void ContextCondenser::render_anchored() {
    // Render the cached TaskLedger + scratchpad + module snapshots into a single stable
    // system message. If a TaskLedger is present, it renders as clean, structured Markdown
    // so the LLM can directly track milestones and progress on every turn.
    std::string content;
    if (anchored_ledger_.has_value() && (!anchored_ledger_->steps.empty() || !anchored_ledger_->objective.empty())) {
        content = anchored_ledger_->render_markdown();

        // Append scratchpad working memory details if non-empty
        bool has_pad_details = false;
        std::string pad_md;
        if (!anchored_scratchpad_.active_objective.empty() && anchored_scratchpad_.active_objective != anchored_ledger_->objective) {
            pad_md += "- **Active Objective:** " + anchored_scratchpad_.active_objective + "\n";
            has_pad_details = true;
        }
        if (!anchored_scratchpad_.current_hypothesis.empty()) {
            pad_md += "- **Current Hypothesis:** " + anchored_scratchpad_.current_hypothesis + "\n";
            has_pad_details = true;
        }
        if (!anchored_scratchpad_.next_immediate_action.empty()) {
            pad_md += "- **Next Immediate Action:** " + anchored_scratchpad_.next_immediate_action + "\n";
            has_pad_details = true;
        }
        if (!anchored_scratchpad_.verified_facts.empty()) {
            pad_md += "- **Verified Facts:**\n";
            for (const auto& fact : anchored_scratchpad_.verified_facts) {
                pad_md += "  * " + fact + "\n";
            }
            has_pad_details = true;
        }
        if (!anchored_scratchpad_.failed_approaches_do_not_repeat.empty()) {
            pad_md += "- **Failed Approaches (Do NOT Repeat):**\n";
            for (const auto& fa : anchored_scratchpad_.failed_approaches_do_not_repeat) {
                pad_md += "  * " + fa + "\n";
            }
            has_pad_details = true;
        }
        if (has_pad_details) {
            content += "\n### 📝 Scratchpad Notes:\n" + pad_md;
        }
    } else {
        Json rendered = Json::object();
        to_json(rendered["scratchpad"], anchored_scratchpad_);
        content = rendered.dump();
    }

    // Append module snapshots if non-empty
    if (!anchored_snapshots_.empty()) {
        Json snapshots = Json::object();
        for (const auto& [id, snap] : anchored_snapshots_) {
            snapshots[id] = snap;
        }
        if (!snapshots.empty()) {
            content += "\n\n### 📦 Module Snapshots:\n```json\n" + snapshots.dump() + "\n```\n";
        }
    }

    anchored_.role = Role::system;
    anchored_.content = std::move(content);
    anchored_.images.clear();
}

std::vector<Message> ContextCondenser::build_messages() const {
    std::vector<Message> messages;

    // 1. Pinned prefix [0..P]: system prompt message, then recipe schema message.
    messages.push_back(Message{Role::system, system_prompt_, {}});
    messages.push_back(Message{Role::system, recipe_schema_, {}});

    // 2. Anchored block [P+1..S]: one system message with the TaskLedger/scratchpad + snapshots.
    messages.push_back(anchored_);

    // 3. The initial user request (persisted across condensation and turns).
    if (!user_prompt_.empty()) {
        messages.push_back(Message{Role::user, user_prompt_, {}});
    }

    // 4. Rolling tail [S+1..end]: each recorded interaction becomes an assistant/tool
    //    message pair, emitted in recorded order (oldest first). Bound active vision
    //    attachments to the most recent interactions to preserve context budget.
    constexpr std::size_t kMaxActiveObservationImages = 2;
    std::size_t first_img_idx = tail_.size();
    std::size_t collected_images = 0;
    for (std::size_t idx = tail_.size(); idx > 0; --idx) {
        const auto& img_vec = tail_[idx - 1].images.empty() ? tail_[idx - 1].result.images
                                                            : tail_[idx - 1].images;
        if (!img_vec.empty()) {
            if (collected_images >= kMaxActiveObservationImages) break;
            first_img_idx = idx - 1;
            collected_images += img_vec.size();
        }
    }

    for (std::size_t i = 0; i < tail_.size(); ++i) {
        const ToolInteraction& interaction = tail_[i];
        Json call = Json::object();
        call["module"] = interaction.module;
        call["action"] = interaction.action;
        call["args"] = interaction.args;
        messages.push_back(Message{Role::assistant, call.dump(), {}});

        std::vector<std::string> obs_images;
        if (i >= first_img_idx) {
            obs_images = !interaction.images.empty() ? interaction.images
                                                     : interaction.result.images;
        }
        messages.push_back(Message{Role::tool, interaction.result.llm_facing_output, std::move(obs_images)});
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
    guidance_.clear();
    // Head+tail-truncate the LLM-facing output before it enters the tail; the full
    // text (if oversized) lands in spill_ keyed by the ref embedded in the view.
    ToolInteraction stored = interaction;
    if (stored.images.empty() && !stored.result.images.empty()) {
        stored.images = stored.result.images;
    }
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

void ContextCondenser::clear_guidance() {
    guidance_.clear();
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

bool ContextCondenser::has_collapsible_history() const noexcept {
    return !tail_.empty();
}

void ContextCondenser::condense() {
    // Wipe policy (Req 2.4): the pinned prefix (system_prompt_ / recipe_schema_) is
    // never touched; the anchored block is refreshed from the most recent
    // set_anchored() inputs via the shared renderer so it equals that rendering; the
    // rolling tail, pending guidance, and running summary are cleared.
    render_anchored();
    tail_.clear();
    guidance_.clear();
    running_summary_.clear();
}

}  // namespace aquila
