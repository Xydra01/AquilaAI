add_library(aquila_core STATIC
    version.cpp
    deps_probe.cpp)
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
