#include "aquila/agent/run_record.hpp"

namespace aquila {

using namespace json_io;

void to_json(Json& j, const RunRecord& v) {
    j = Json::object();
    j["task_id"] = v.task_id;
    j["mode"] = v.mode;
    j["instance_id"] = v.instance_id;
    j["step_index"] = v.step_index;
    j["ground_truth"] = v.ground_truth;
    // last_interaction is optional; reuse the M1 ToolInteraction serializer and
    // emit the key only when present so an empty record round-trips byte-equal.
    if (v.last_interaction) {
        Json interaction;
        to_json(interaction, *v.last_interaction);
        j["last_interaction"] = std::move(interaction);
    }
}

void from_json(const Json& j, RunRecord& v, const std::string& path) {
    expect_object(j, path);
    reject_unknown(j, path,
                   {"task_id", "mode", "instance_id", "step_index", "ground_truth",
                    "last_interaction"});
    v.task_id = read_string(require(j, path, "task_id"), child_path(path, "task_id"));
    v.mode = read_string(require(j, path, "mode"), child_path(path, "mode"));
    v.instance_id = read_string(require(j, path, "instance_id"), child_path(path, "instance_id"));
    v.step_index = read_u64(require(j, path, "step_index"), child_path(path, "step_index"));
    v.ground_truth = read_object(require(j, path, "ground_truth"), child_path(path, "ground_truth"));

    v.last_interaction.reset();
    if (const auto it = j.find("last_interaction"); it != j.end()) {
        const auto interaction_path = child_path(path, "last_interaction");
        ToolInteraction interaction;
        from_json(*it, interaction, interaction_path);
        v.last_interaction = std::move(interaction);
    }
}

}  // namespace aquila
