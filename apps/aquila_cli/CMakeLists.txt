add_executable(aquila_cli main.cpp)
target_link_libraries(aquila_cli PRIVATE aquila::core)
aquila_set_warnings(aquila_cli)

string(REPLACE "." "\\." _version_re "${PROJECT_VERSION}")
add_test(NAME cli.version COMMAND aquila_cli --version)
set_tests_properties(cli.version PROPERTIES
    PASS_REGULAR_EXPRESSION "^aquila ${_version_re}[\r\n]*$")
aquila_test_env(cli.version)
