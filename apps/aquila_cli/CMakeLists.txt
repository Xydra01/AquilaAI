add_library(aquila_cli_lib STATIC cli_app.cpp)
target_include_directories(aquila_cli_lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(aquila_cli_lib PUBLIC aquila::core)
aquila_set_warnings(aquila_cli_lib)

add_executable(aquila_cli main.cpp)
target_link_libraries(aquila_cli PRIVATE aquila_cli_lib)
aquila_set_warnings(aquila_cli)

string(REPLACE "." "\\." _version_re "${PROJECT_VERSION}")
add_test(NAME cli.version COMMAND aquila_cli --version)
set_tests_properties(cli.version PROPERTIES
    PASS_REGULAR_EXPRESSION "^aquila ${_version_re}[\r\n]*$")
aquila_test_env(cli.version)

add_test(NAME cli.help COMMAND aquila_cli --help)
set_tests_properties(cli.help PROPERTIES
    PASS_REGULAR_EXPRESSION "Usage: aquila_cli")
aquila_test_env(cli.help)

add_test(NAME cli.list_recipes COMMAND aquila_cli list-recipes)
set_tests_properties(cli.list_recipes PROPERTIES
    PASS_REGULAR_EXPRESSION "Builtin Recipe Cartridges \\(17\\):")
aquila_test_env(cli.list_recipes)

add_test(NAME cli.list_modules COMMAND aquila_cli list-modules)
set_tests_properties(cli.list_modules PROPERTIES
    PASS_REGULAR_EXPRESSION "\\[WorkspaceModule\\]")
aquila_test_env(cli.list_modules)
