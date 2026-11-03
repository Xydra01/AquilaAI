# tree-sitter core + grammars, pinned by URL + SHA256. Only the sources are used
# (SOURCE_SUBDIR points at a directory without a CMakeLists.txt), so the
# upstream build scripts never run.
include(FetchContent)

function(aquila_fetch_sources name url sha256)
    FetchContent_Declare(${name} URL ${url} URL_HASH SHA256=${sha256}
        SOURCE_SUBDIR aquila-no-cmake EXCLUDE_FROM_ALL)
    FetchContent_MakeAvailable(${name})
    set(${name}_SOURCE_DIR "${${name}_SOURCE_DIR}" PARENT_SCOPE)
endfunction()

aquila_fetch_sources(ts_core
    https://github.com/tree-sitter/tree-sitter/archive/refs/tags/v0.27.1.tar.gz
    982cd3d4d9eb7be18c243240a622423fd2e4ecb4bec2cd98832c2f3fa1f0f333)
aquila_fetch_sources(ts_c
    https://github.com/tree-sitter/tree-sitter-c/archive/refs/tags/v0.24.2.tar.gz
    2eeb4db31f8fa0865e45488503d13403923bcb485a1bdb637abff8c42dd97364)
aquila_fetch_sources(ts_cpp
    https://github.com/tree-sitter/tree-sitter-cpp/archive/refs/tags/v0.23.4.tar.gz
    7a2c55afe3028f4105f25762ea58cc16537d1f5a1dcd9cca90410b3cd5d46051)
aquila_fetch_sources(ts_python
    https://github.com/tree-sitter/tree-sitter-python/archive/refs/tags/v0.25.0.tar.gz
    4609a3665a620e117acf795ff01b9e965880f81745f287a16336f4ca86cf270c)

# tree-sitter calls grammar scanners through `void *(*)(void)` pointers while the
# scanners are defined with unprototyped `()`; UBSan's -fsanitize=function flags
# that upstream C mismatch. Only that check is disabled, only for these targets.
set(_ts_c_flags "")
if(AQUILA_UBSAN AND NOT MSVC)
    set(_ts_c_flags -fno-sanitize=function)
endif()

add_library(tree_sitter STATIC "${ts_core_SOURCE_DIR}/lib/src/lib.c")
target_compile_options(tree_sitter PRIVATE ${_ts_c_flags})
target_include_directories(tree_sitter SYSTEM
    PUBLIC "${ts_core_SOURCE_DIR}/lib/include"
    PRIVATE "${ts_core_SOURCE_DIR}/lib/src")
set_target_properties(tree_sitter PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON POSITION_INDEPENDENT_CODE ON)
if(NOT WIN32)
    target_compile_definitions(tree_sitter PRIVATE _POSIX_C_SOURCE=200112L _DEFAULT_SOURCE)
endif()

# Grammar parsers are large generated C files; they get no warning flags.
function(aquila_grammar target dir)
    set(srcs "${dir}/src/parser.c")
    if(EXISTS "${dir}/src/scanner.c")
        list(APPEND srcs "${dir}/src/scanner.c")
    endif()
    add_library(${target} STATIC ${srcs})
    target_include_directories(${target} SYSTEM PRIVATE "${dir}/src")
    set_target_properties(${target} PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON POSITION_INDEPENDENT_CODE ON)
    if(MSVC)
        target_compile_options(${target} PRIVATE /W0 /bigobj)
    else()
        target_compile_options(${target} PRIVATE -w ${_ts_c_flags})
    endif()
endfunction()

aquila_grammar(tree_sitter_c "${ts_c_SOURCE_DIR}")
aquila_grammar(tree_sitter_cpp "${ts_cpp_SOURCE_DIR}")
aquila_grammar(tree_sitter_python "${ts_python_SOURCE_DIR}")
