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

TEST_CASE("persona: verify_persona_quality utility gates", "[persona]") {
    test::TempDir tmp;
    ModuleContext ctx;
    ctx.workspace_root = tmp.path();

    PersonaModule mod(ctx);

    // 1. Without active persona fails
    auto res = mod.execute_action("verify_persona_quality", Json::object());
    CHECK_FALSE(res.success);
    CHECK(res.error_code == "no_active_persona");

    mod.execute_action("load_persona", Json::object({
        {"persona_id", "socrates"},
        {"display_name", "Socrates"}
    }));

    // 2. Calling before finalize fails
    res = mod.execute_action("verify_persona_quality", Json::object({
        {"require_finalized", true}
    }));
    CHECK_FALSE(res.success);
    CHECK(res.error_code == "persona_not_finalized");

    // 3. Write initialization with assistant leakage
    std::string leaky_init = "# Identity\n\nI am Socrates of Athens. As an AI language model, I do not have personal opinions or feelings about ethics.\n\n# Voice\n\nI speak through the dialectic method.";
    while (leaky_init.size() < 850) {
        leaky_init += " The unexamined life is not worth living in the agora.";
    }
    mod.execute_action("write_initialization", Json::object({
        {"file_path", "initialization.md"},
        {"content", leaky_init}
    }));
    mod.execute_action("finalize_persona", Json::object({
        {"greeting", "Greetings, fellow citizen of Athens."},
        {"tagline", "Classical Philosopher"}
    }));

    res = mod.execute_action("verify_persona_quality", Json::object());
    CHECK_FALSE(res.success);
    CHECK(res.error_code == "assistant_leakage_detected");

    // 4. Overwrite with rich, immersive, authentic persona lore
    mod.execute_action("load_persona", Json::object({
        {"persona_id", "socrates_clean"},
        {"display_name", "Socrates of Athens"}
    }));

    std::string immersive_init = R"(# Identity and Character Lore
I am Socrates of Athens, son of Sophroniscus the stonemason and Phaenarete the midwife. I wander barefoot through the bustling Agora, engaging citizens in dialectical inquiry not to teach dogma, but to examine whether our beliefs withstand relentless logical scrutiny.

# Dialectical Voice and Philosophy
My speech is calm, persistent, and grounded in the elenctic method. I begin with courteous curiosity, drawing out definitions from my interlocutors before highlighting internal contradictions with gentle irony. I profess no specialized wisdom myself, claiming only to know that I know nothing.

# Behavioral Guidelines and Mannerisms
I never claim divine revelation, but listen closely to my daimonion—a subtle inner voice warning me against foolish courses of action. I ask probing questions rather than declaring edicts. I remain steadfastly indifferent to material luxury, wealth, and aristocratic flattery.
)";
    while (immersive_init.size() < 900) {
        immersive_init += " We must examine our souls and strive for virtue above all earthly possessions.\n";
    }

    mod.execute_action("write_initialization", Json::object({
        {"file_path", "initialization.md"},
        {"content", immersive_init}
    }));
    mod.execute_action("finalize_persona", Json::object({
        {"greeting", "Greetings, fellow citizen of Athens."},
        {"tagline", "Classical Philosopher"}
    }));

    res = mod.execute_action("verify_persona_quality", Json::object());
    CHECK(res.success);
    CHECK(res.llm_facing_output.find("verified successfully") != std::string::npos);
}

