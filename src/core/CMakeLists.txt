add_library(aquila_core STATIC
    version.cpp
    deps_probe.cpp
    json.cpp
    types/message.cpp
    types/action.cpp
    types/tool_interaction.cpp
    types/scratchpad.cpp
    types/recipe.cpp
    inference/ollama_wire.cpp
    inference/ollama_backend.cpp
    workspace/syntax.cpp
    workspace/path_firewall.cpp
    canvas/diff.cpp
    canvas/canvas_buffer.cpp
    modules/schema_check.cpp
    modules/module.cpp
    modules/registry.cpp
    modules/workspace_module.cpp
    exec/process_common.cpp
    exec/process_win.cpp
    exec/process_posix.cpp
    exec/diagnostics.cpp
    modules/execution_module.cpp
    modules/builtin.cpp)
add_library(aquila::core ALIAS aquila_core)

target_include_directories(aquila_core PUBLIC include)
target_compile_definitions(aquila_core PRIVATE AQUILA_VERSION="${PROJECT_VERSION}")
target_link_libraries(aquila_core
    PUBLIC
        nlohmann_json::nlohmann_json
    PRIVATE
        fmt::fmt
        spdlog::spdlog
        pantor::inja
        httplib::httplib
        tree_sitter
        tree_sitter_c
        tree_sitter_cpp
        tree_sitter_python)
aquila_set_warnings(aquila_core)
