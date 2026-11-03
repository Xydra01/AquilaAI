# Third-party dependencies, pinned by URL + SHA256 (a changed archive fails configure).
# Versions are recorded in docs/recon/RECON_MAP.md (section 1, "C++ dependencies").
include(FetchContent)

set(FETCHCONTENT_QUIET ON)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)

FetchContent_Declare(nlohmann_json
    URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
    URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
    SYSTEM EXCLUDE_FROM_ALL)

FetchContent_Declare(fmt
    URL https://github.com/fmtlib/fmt/releases/download/12.2.0/fmt-12.2.0.zip
    URL_HASH SHA256=a2f4a8d51178f954e4c339007f77edd76ba0cb2e36f87a48e5a5403d9be5878f
    SYSTEM EXCLUDE_FROM_ALL)

FetchContent_Declare(spdlog
    URL https://github.com/gabime/spdlog/archive/refs/tags/v1.17.0.tar.gz
    URL_HASH SHA256=d8862955c6d74e5846b3f580b1605d2428b11d97a410d86e2fb13e857cd3a744
    SYSTEM EXCLUDE_FROM_ALL)

FetchContent_Declare(inja
    URL https://github.com/pantor/inja/archive/refs/tags/v3.5.0.tar.gz
    URL_HASH SHA256=a5f0266673c59028eab6ceeddd8b862c70abfeb32fb7a5387c16bf46f3269ab2
    SYSTEM EXCLUDE_FROM_ALL)

FetchContent_Declare(httplib
    URL https://github.com/yhirose/cpp-httplib/archive/refs/tags/v0.64.0.tar.gz
    URL_HASH SHA256=1ada413782af5e67e80452c39b7c90beb6fa4fc8341e18c0896bf95684b9a620
    SYSTEM EXCLUDE_FROM_ALL)

FetchContent_Declare(Catch2
    URL https://github.com/catchorg/Catch2/archive/refs/tags/v3.16.1.tar.gz
    URL_HASH SHA256=d16bd1b8b2364918bd472cb216394acb93bde6784890df0d91bccfb3f28d777d
    SYSTEM EXCLUDE_FROM_ALL)

set(JSON_Install OFF CACHE BOOL "" FORCE)

set(FMT_INSTALL OFF CACHE BOOL "" FORCE)
set(FMT_MODULE OFF CACHE BOOL "" FORCE)

set(SPDLOG_FMT_EXTERNAL ON CACHE BOOL "" FORCE)
set(SPDLOG_INSTALL OFF CACHE BOOL "" FORCE)

set(INJA_USE_EMBEDDED_JSON OFF CACHE BOOL "" FORCE)
set(INJA_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(BUILD_BENCHMARK OFF CACHE BOOL "" FORCE)
set(INJA_INSTALL OFF CACHE BOOL "" FORCE)
set(INJA_EXPORT OFF CACHE BOOL "" FORCE)

# HTTPS/compression stay off until a milestone needs them; keeps builds reproducible
# regardless of what happens to be installed on the machine.
set(HTTPLIB_USE_OPENSSL_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_ZLIB_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_BROTLI_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_ZSTD_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_INSTALL OFF CACHE BOOL "" FORCE)

set(CATCH_INSTALL_DOCS OFF CACHE BOOL "" FORCE)
set(CATCH_INSTALL_EXTRAS OFF CACHE BOOL "" FORCE)

FetchContent_MakeAvailable(nlohmann_json fmt spdlog inja httplib Catch2)
