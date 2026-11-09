// tests/unit/run_logger_test.cpp
#include "aquila/logging/run_logger.hpp"

#include <catch2/catch_test_macros.hpp>
#include <filesystem>
#include <fstream>
#include <string>

using namespace aquila::logging;
using namespace aquila;

TEST_CASE("RunLogger creates dual-format .log and .jsonl files with full thinking trace", "[run_logger]") {
    const std::filesystem::path temp_dir = std::filesystem::temp_directory_path() / "aquila_logger_test";
    std::error_code ec;
    std::filesystem::remove_all(temp_dir, ec);
    std::filesystem::create_directories(temp_dir, ec);

    {
        RunLogger logger;
        REQUIRE(logger.start_session("fn_dev_implement", "task", "unit_test_inst",
                                     "Implement a robust non-interactive weather parser", temp_dir));

        REQUIRE(logger.is_active());
        const auto log_file = logger.log_path();
        const auto jsonl_file = logger.jsonl_path();

        CHECK(std::filesystem::exists(log_file));
        CHECK(std::filesystem::exists(jsonl_file));
        CHECK(log_file.extension() == ".log");
        CHECK(jsonl_file.extension() == ".jsonl");

        // Turn 1
        logger.log_turn_start(1);

        // Multi-paragraph thinking trace
        const std::string thinking_text =
            "Step 1: I need to analyze the requirements.\n"
            "Step 2: External requests should have a fallback test harness.\n"
            "Step 3: Strictly non-interactive; never call input(). Use sys.argv if supplied.";
        logger.log_thinking(1, thinking_text, "strategic_plan");

        // LLM response
        logger.log_llm_response(1, "{\"thought\": \"creating script\", \"module\": \"WorkspaceModule\", \"action\": \"create_file\", \"args\": {\"path\": \"weather.py\"}}", true, "creating script");

        // Action call
        Json args = Json::object();
        args["path"] = "weather.py";
        args["content"] = "import sys\nprint('Weather: 72F Sunny')";
        logger.log_action_call(1, "WorkspaceModule", "create_file", args);

        // Action result
        logger.log_action_result(1, "WorkspaceModule", "create_file", true, "Created file weather.py (35 bytes)");

        // Exit gate
        logger.log_exit_gate("ExecutionModule", "verify_implementation", true, "Script weather.py executed cleanly with exit code 0.");

        // Session end
        logger.log_session_end(true, "success", "Weather parser created and verified.", 1);
    }

    // Inspect files on disk
    const auto logs_dir = temp_dir / "Agent-Logs";
    REQUIRE(std::filesystem::exists(logs_dir));

    bool found_log = false;
    bool found_jsonl = false;

    for (const auto& entry : std::filesystem::directory_iterator(logs_dir)) {
        if (entry.path().extension() == ".log") {
            found_log = true;
            std::ifstream in(entry.path());
            std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
            CHECK(content.find("AQUILA AI FRAMEWORK - AGENT SESSION LOG") != std::string::npos);
            CHECK(content.find("fn_dev_implement") != std::string::npos);
            CHECK(content.find("[THINKING (strategic_plan)]") != std::string::npos);
            CHECK(content.find("Strictly non-interactive; never call input()") != std::string::npos);
            CHECK(content.find("WorkspaceModule::create_file") != std::string::npos);
            CHECK(content.find("RECIPE EXIT GATE: ExecutionModule::verify_implementation [PASSED]") != std::string::npos);
            CHECK(content.find("SESSION FINISHED: [SUCCEEDED]") != std::string::npos);
        } else if (entry.path().extension() == ".jsonl") {
            found_jsonl = true;
            std::ifstream in(entry.path());
            std::string line;
            int count = 0;
            bool has_session_start = false;
            bool has_thinking = false;
            bool has_exit_gate = false;
            bool has_session_end = false;

            while (std::getline(in, line)) {
                if (line.empty()) continue;
                count++;
                auto doc = Json::parse(line);
                std::string ev = doc["event"].get<std::string>();
                if (ev == "session_start") has_session_start = true;
                if (ev == "thinking_trace") {
                    has_thinking = true;
                    CHECK(doc["thinking_chars"].get<int>() > 50);
                    CHECK(doc["thinking"].get<std::string>().find("never call input()") != std::string::npos);
                }
                if (ev == "exit_gate") has_exit_gate = true;
                if (ev == "session_end") has_session_end = true;
            }
            CHECK(has_session_start);
            CHECK(has_thinking);
            CHECK(has_exit_gate);
            CHECK(has_session_end);
            CHECK(count >= 5);
        }
    }

    CHECK(found_log);
    CHECK(found_jsonl);

    std::filesystem::remove_all(temp_dir, ec);
}

