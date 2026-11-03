#pragma once

#include "aquila/json.hpp"
#include "aquila/types/action.hpp"
#include "aquila/types/message.hpp"
#include "aquila/types/recipe.hpp"
#include "aquila/types/scratchpad.hpp"
#include "aquila/types/tool_interaction.hpp"

#include <filesystem>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <string_view>

namespace aquila::test {

inline std::filesystem::path fixture_dir() {
    return std::filesystem::path(AQUILA_FIXTURE_DIR);
}

inline std::string read_bytes(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot open " + path.string());
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}

inline bool starts_with(std::string_view s, std::string_view prefix) {
    return s.substr(0, prefix.size()) == prefix;
}

// Parses `text` as the type named by the fixture's file-name prefix and returns
// its canonical serialization.
inline std::string canonical_by_prefix(std::string_view file_name, std::string_view text) {
    if (starts_with(file_name, "message_")) return to_canonical_string(parse<Message>(text));
    if (starts_with(file_name, "action_call_")) return to_canonical_string(parse<ActionCall>(text));
    if (starts_with(file_name, "action_schema_")) return to_canonical_string(parse<ActionSchema>(text));
    if (starts_with(file_name, "action_result_")) return to_canonical_string(parse<ActionResult>(text));
    if (starts_with(file_name, "tool_interaction_")) return to_canonical_string(parse<ToolInteraction>(text));
    if (starts_with(file_name, "checklist_item_")) return to_canonical_string(parse<ChecklistItem>(text));
    if (starts_with(file_name, "scratchpad_")) return to_canonical_string(parse<AgentScratchpad>(text));
    if (starts_with(file_name, "recipe_")) return to_canonical_string(parse<RecipeCartridge>(text));
    throw std::runtime_error("no type mapped for fixture " + std::string(file_name));
}

}  // namespace aquila::test
