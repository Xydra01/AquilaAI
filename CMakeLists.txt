cmake_minimum_required(VERSION 3.28)

project(AquilaCpp VERSION 0.0.1 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)

if(WIN32)
    # Windows 10 is the minimum target (cpp-httplib requires it; llvm-mingw defaults lower).
    add_compile_definitions(_WIN32_WINNT=0x0A00 WINVER=0x0A00)
endif()

option(AQUILA_BUILD_GUI "Build the Qt 6 Widgets GUI (requires the Qt MSVC SDK)" OFF)
option(AQUILA_REQUIRE_WEBENGINE "Fail configure if Qt6 WebEngineWidgets is not installed" OFF)
option(AQUILA_ENABLE_CUDA "Build the CUDA smoke test (requires nvcc + MSVC host compiler)" OFF)
option(AQUILA_SANITIZER_TESTS "Register the deliberate-defect sanitizer tests" ON)
option(AQUILA_LIVE_TESTS "Register tests that need a running Ollama server (never in CI)" OFF)
set(AQUILA_SANITIZE "" CACHE STRING "Semicolon list of sanitizers: address, undefined, leak")

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

# Sanitizer flags must be set before dependencies are fetched so third-party code
# is instrumented the same way (MSVC rejects mixing ASan and non-ASan STL objects).
include(AquilaSanitizers)
include(AquilaWarnings)
include(AquilaTestEnv)
include(AquilaDeps)
include(AquilaTreeSitter)
include(AquilaRapidCheck)
include(AquilaLlamaCpp)
include(AquilaSqlite)

if(AQUILA_ENABLE_CUDA)
    enable_language(CUDA)
endif()

enable_testing()

add_subdirectory(src/core)
add_subdirectory(apps/aquila_cli)
if(AQUILA_BUILD_GUI)
    add_subdirectory(apps/aquila_gui)
endif()
add_subdirectory(tests)
