#include "aquila/modules/module.hpp"

#include "aquila/modules/schema_check.hpp"

namespace aquila {

std::uint64_t estimate_tokens(std::string_view text) noexcept {
    return (text.size() + 3) / 4;
}

ActionResult ModuleBase::ok(std::string text) {
    ActionResult r;
    r.success = true;
    r.token_estimate = estimate_tokens(text);
    r.llm_facing_output = std::move(text);
    return r;
}

ActionResult ModuleBase::fail(std::string code, std::string text) {
    ActionResult r;
    r.success = false;
    r.error_code = std::move(code);
    r.token_estimate = estimate_tokens(text);
    r.llm_facing_output = std::move(text);
    return r;
}

ActionResult ModuleBase::execute_action(const std::string& action_name, const Json& args) {
    for (const auto& schema : get_actions()) {
        if (schema.action_name != action_name) continue;
        try {
            check_schema(schema.parameters_json_schema, args);
        } catch (const SchemaError& e) {
            return fail("invalid_args", std::string("invalid args for ") + action_name + ": " + e.what());
        }
        return run(action_name, args);
    }
    return fail("unknown_action", module_id() + " has no action '" + action_name + "'");
}

}  // namespace aquila
