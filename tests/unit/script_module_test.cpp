#include "aquila/plugins/script_module.hpp"
#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>
#include <fstream>

using namespace aquila;
using namespace aquila::plugins;

TEST_CASE("script_module: manifest parsing and subprocess execution via stdin/stdout", "[plugins]") {
    test::TempDir tmp;
    const std::string helper_path = AQUILA_PROC_HELPER;

    // Create a manifest.json
    Json manifest = Json::object({
        {"module_id", "EchoPlugin"},
        {"description", "Test plugin using proc helper"},
        {"actions", Json::array({
            Json::object({
                {"name", "echo_json"},
                {"description", "Echoes input arguments back"},
                {"parameters_json_schema", Json::object({
                    {"type", "object"},
                    {"properties", Json::object({
                        {"msg", Json::object({{"type", "string"}})}
                    })}
                })},
                {"command", Json::array({helper_path, "echo-stdin"})},
                {"timeout_s", 10.0}
            })
        })}
    });

    std::ofstream out(tmp.path() / "manifest.json");
    out << manifest.dump(2);
    out.close();

    ScriptModule mod(tmp.path());
    CHECK(mod.module_id() == "EchoPlugin");
    REQUIRE(mod.get_actions().size() == 1);
    CHECK(mod.get_actions()[0].action_name == "echo_json");

    // Execute action
    const auto res = mod.execute_action("echo_json", Json::object({
        {"msg", "hello plugin architecture"}
    }));
    REQUIRE(res.success);
    CHECK(res.llm_facing_output.find("hello plugin architecture") != std::string::npos);

    // Unknown action returns failure
    const auto bad_res = mod.execute_action("non_existent", Json::object());
    CHECK_FALSE(bad_res.success);
    CHECK(bad_res.error_code == "unknown_action");
}

