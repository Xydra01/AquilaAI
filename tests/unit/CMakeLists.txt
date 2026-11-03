add_executable(aquila_unit_tests
    deps_probe_test.cpp)
target_link_libraries(aquila_unit_tests PRIVATE aquila::core Catch2::Catch2WithMain)
aquila_set_warnings(aquila_unit_tests)

add_test(NAME unit COMMAND aquila_unit_tests --reporter console)
aquila_test_env(unit)
