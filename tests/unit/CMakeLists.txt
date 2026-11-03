add_executable(aquila_unit_tests
    deps_probe_test.cpp
    types_roundtrip_test.cpp
    types_errors_test.cpp
    recipe_doc_test.cpp
    mutation_robustness_test.cpp)
target_link_libraries(aquila_unit_tests PRIVATE aquila::core Catch2::Catch2WithMain)
target_compile_definitions(aquila_unit_tests PRIVATE
    AQUILA_FIXTURE_DIR="${PROJECT_SOURCE_DIR}/tests/fixtures"
    AQUILA_DESIGN_DOC="${PROJECT_SOURCE_DIR}/docs/design/aquila-cpp-design.md")
aquila_set_warnings(aquila_unit_tests)

add_test(NAME unit COMMAND aquila_unit_tests --reporter console)
aquila_test_env(unit)
