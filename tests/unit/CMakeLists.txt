add_executable(aquila_unit_tests
    deps_probe_test.cpp
    types_roundtrip_test.cpp
    types_errors_test.cpp
    recipe_doc_test.cpp
    mutation_robustness_test.cpp
    ollama_wire_test.cpp
    ollama_backend_test.cpp
    syntax_test.cpp
    registry_test.cpp
    path_firewall_test.cpp
    diff_test.cpp
    canvas_buffer_test.cpp
    workspace_module_test.cpp
    python_oracle_test.cpp
    process_test.cpp
    diagnostics_test.cpp
    execution_module_test.cpp
    runtime_tier_test.cpp
    run_record_test.cpp
    context_condenser_test.cpp
    orchestrator_module_test.cpp
    agent_loop_test.cpp
    recipe_cartridge_test.cpp)
target_link_libraries(aquila_unit_tests PRIVATE
    aquila::core httplib::httplib Catch2::Catch2WithMain rapidcheck_catch)
target_compile_definitions(aquila_unit_tests PRIVATE
    AQUILA_FIXTURE_DIR="${PROJECT_SOURCE_DIR}/tests/fixtures"
    AQUILA_RECIPE_DIR="${PROJECT_SOURCE_DIR}/src/core/agent/recipes"
    AQUILA_DESIGN_DOC="${PROJECT_SOURCE_DIR}/docs/design/aquila-cpp-design.md"
    AQUILA_PROC_HELPER="$<TARGET_FILE:aquila_proc_helper>")
add_dependencies(aquila_unit_tests aquila_proc_helper)
aquila_set_warnings(aquila_unit_tests)

add_test(NAME unit COMMAND aquila_unit_tests --reporter console)
aquila_test_env(unit)
