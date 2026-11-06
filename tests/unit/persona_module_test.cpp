#include "aquila/persona/persona_module.hpp"
#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>
#include <fstream>
#include <string>

using namespace aquila;
using namespace aquila::persona;

TEST_CASE("persona: full persona module workflow and quality gates", "[persona]") {
    test::TempDir tmp;
    ModuleContext ctx;
    ctx.workspace_root = tmp.path();

    PersonaModule mod(ctx);
    CHECK_FALSE(mod.has_active_persona());

    // 1. Calling write_initialization before load fails with no_active_persona
    auto res = mod.execute_action("write_initialization", Json::object({
        {"file_path", "initialization.md"},
        {"content", "Too short"}
    }));
    CHECK_FALSE(res.success);
    CHECK(res.error_code == "no_active_persona");

    // 2. Load / initialize persona
    res = mod.execute_action("load_persona", Json::object({
        {"persona_id", "elena-ai-engineer"},
        {"instance_id", "test_inst"},
        {"display_name", "Elena Rostova"}
    }));
    REQUIRE(res.success);
    CHECK(mod.has_active_persona());
    CHECK(mod.persona().display_name == "Elena Rostova");
    CHECK(std::filesystem::exists(mod.persona_dir() / "persona.json"));

    // 3. Test invalid file_path
    res = mod.execute_action("write_initialization", Json::object({
        {"file_path", "other.txt"},
        {"content", std::string(850, 'x')}
    }));
    CHECK_FALSE(res.success);
    CHECK(res.error_code == "invalid_file_path");

    // 4. Test quality gate: reject < 800 chars
    res = mod.execute_action("write_initialization", Json::object({
        {"file_path", "initialization.md"},
        {"content", std::string(799, 'a')}
    }));
    CHECK_FALSE(res.success);
    CHECK(res.error_code == "init_doc_too_short");

    // 5. Write valid initialization (> 800 chars)
    const std::string valid_init =
        "You are Elena Rostova, a senior systems and distributed runtime engineer.\n" +
        std::string(800, 'Z') + "\nAlways answer with deep technical precision and concise tone.";
    res = mod.execute_action("write_initialization", Json::object({
        {"file_path", "initialization.md"},
        {"content", valid_init}
    }));
    REQUIRE(res.success);
    CHECK(std::filesystem::exists(mod.initialization_file()));

    // 6. Test duplicate write block (OS BLOCK matching Python)
    res = mod.execute_action("write_initialization", Json::object({
        {"file_path", "initialization.md"},
        {"content", valid_init + " more text"}
    }));
    CHECK_FALSE(res.success);
    CHECK(res.error_code == "already_written");
    CHECK(res.llm_facing_output.find("OS BLOCK: initialization.md is already written") != std::string::npos);

    // 7. Update user preferences
    res = mod.execute_action("update_preferences", Json::object({
        {"preferences", "Prefers C++20 and strict value semantics."}
    }));
    REQUIRE(res.success);
    CHECK(std::filesystem::exists(mod.preferences_file()));

    // 8. Finalize persona
    res = mod.execute_action("finalize_persona", Json::object({
        {"greeting", "Greetings! Let us analyze the runtime architecture."},
        {"tagline", "Senior Systems Architect"}
    }));
    REQUIRE(res.success);
    CHECK(mod.persona().build_complete);
    CHECK(mod.persona().greeting == "Greetings! Let us analyze the runtime architecture.");
    CHECK(mod.persona().tagline == "Senior Systems Architect");

    // 9. Chat as persona
    res = mod.execute_action("chat_as_persona", Json::object({
        {"user_message", "How should we design the memory layout?"},
        {"assistant_reply", "By enforcing deterministic value semantics with zero owning pointers."}
    }));
    REQUIRE(res.success);
    CHECK(std::filesystem::exists(mod.chat_history_file()));

    // 10. Snapshot round-trip
    const auto snapshot = mod.export_state_snapshot();
    CHECK(snapshot["has_active_persona"] == true);
    CHECK(snapshot["persona_id"] == "elena-ai-engineer");
    CHECK(snapshot["display_name"] == "Elena Rostova");
    CHECK(snapshot["build_complete"] == true);

    PersonaModule mod2(ctx);
    mod2.restore_state_snapshot(snapshot);
    CHECK(mod2.has_active_persona());
    CHECK(mod2.persona().display_name == "Elena Rostova");
    CHECK(mod2.persona().build_complete);
}

