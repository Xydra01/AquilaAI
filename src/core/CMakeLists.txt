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
    inference/ollama_backend.cpp)
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
        httplib::httplib)
aquila_set_warnings(aquila_core)
