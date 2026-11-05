# llama.cpp inference backend (M5), pinned by URL + SHA256 like every other dep
# (cmake/AquilaDeps.cmake). Unlike the header/amalgamation deps, llama.cpp ships
# its own large CMake build plus a CUDA backend, so it needs a per-lane strategy.
#
# Two facts drive the strategy (see .kiro/specs/m5-llamacpp-backend/design.md
# "Build strategy" + docs/recon/RECON_MAP.md section 1):
#   1. CUDA needs the MSVC host compiler (H12): llama.cpp's CUDA backend builds
#      under cl.exe + nvcc, never llvm-mingw clang. So the GPU path is MSVC-only.
#   2. cmake/AquilaSanitizers.cmake applies -fsanitize=... GLOBALLY (add_compile_
#      options), which would instrument all of llama.cpp/ggml too. Building the
#      whole upstream tree (and CUDA) under ASan/UBSan is impractical and not what
#      we test -- we test *our* wrapper. So heavy sanitizer lanes stub the backend,
#      and the one lane that builds it under a sanitizer (linux-san) builds it
#      CPU-only with our sanitizer/warning flags scoped OFF the upstream targets
#      (the per-target flag scoping precedent is cmake/AquilaTreeSitter.cmake).
#
# Per-lane outcome (design lane table):
#   msvc-release       -> BUILD (CPU; CUDA optional)              AQUILA_HAS_LLAMACPP=1
#   msvc-release-cuda  -> BUILD (CUDA: cl+nvcc, sm_89)            AQUILA_HAS_LLAMACPP=1
#   linux-san          -> BUILD (CPU-only, upstream flags scoped) AQUILA_HAS_LLAMACPP=1
#   mingw-san          -> STUB  (clang can't do CUDA; heavy ASan) AQUILA_HAS_LLAMACPP=0
#   msvc-asan          -> STUB  (ASan over all of llama.cpp impractical) AQUILA_HAS_LLAMACPP=0
#
# Contract for the rest of the tree: link the INTERFACE target `aquila_llamacpp`.
# It always carries the compile definition AQUILA_HAS_LLAMACPP (1 when built, 0
# when stubbed); when ON it also carries the llama.cpp link libs + SYSTEM includes.
# TUs guard llama.cpp includes with `#if AQUILA_HAS_LLAMACPP`.

include(FetchContent)

option(AQUILA_LLAMACPP "Build the llama.cpp inference backend" ON)

# Gate: force OFF on lanes that cannot support it so every lane still configures.
# Concrete, detectable condition: any sanitizer build on a Windows/MinGW target
# (that is msvc-asan and mingw-san). The plain Linux clang CPU lane (linux-san)
# keeps building it CPU-only; non-sanitizer lanes (msvc-release[-cuda]) build it.
if(AQUILA_SANITIZE AND (WIN32 OR MINGW))
    set(AQUILA_LLAMACPP OFF CACHE BOOL "Build the llama.cpp inference backend" FORCE)
    message(STATUS "Aquila llama.cpp: forced OFF on this sanitizer lane (stubbed backend)")
endif()

# The interface target every consumer links. Definition is always present.
add_library(aquila_llamacpp INTERFACE)

if(NOT AQUILA_LLAMACPP)
    target_compile_definitions(aquila_llamacpp INTERFACE AQUILA_HAS_LLAMACPP=0)
    message(STATUS "Aquila llama.cpp: backend STUBBED (AQUILA_HAS_LLAMACPP=0)")
    return()
endif()

message(STATUS "Aquila llama.cpp: backend ENABLED (AQUILA_HAS_LLAMACPP=1)")

# --- upstream ggml-org/llama.cpp, pinned (tag b12116) -----------------------
# SHA256 computed from the archive (curl + Get-FileHash), as the other deps were.
# Recorded in docs/recon/RECON_MAP.md section 1 "C++ dependencies".
set(AQUILA_LLAMACPP_TAG "b12116")

# Build only the libraries we need: the `llama` lib, `ggml`, and `common`
# (json_schema_to_grammar lives in common/). No tests/examples/tools/server, no
# HTTPS/curl stack. Option names verified against the b12116 source.
set(LLAMA_BUILD_COMMON   ON  CACHE BOOL "" FORCE)   # json_schema_to_grammar is here
set(LLAMA_BUILD_TESTS    OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TOOLS    OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_SERVER   OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_APP      OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_UI       OFF CACHE BOOL "" FORCE)
set(LLAMA_CURL           OFF CACHE BOOL "" FORCE)   # deprecated upstream; harmless
set(LLAMA_OPENSSL        OFF CACHE BOOL "" FORCE)   # no HTTPS stack needed for common
set(LLAMA_BUILD_MTMD     OFF CACHE BOOL "" FORCE)
set(GGML_BUILD_TESTS     OFF CACHE BOOL "" FORCE)
set(GGML_BUILD_EXAMPLES  OFF CACHE BOOL "" FORCE)
# We link llama.cpp statically into aquila_core; a shared ggml/llama would need its
# DLLs on PATH for the tests. Static keeps the test exes self-contained.
set(BUILD_SHARED_LIBS    OFF CACHE BOOL "" FORCE)

# GPU only on MSVC (H12). sm_89 = RTX 4070. CPU-only everywhere else.
# Default is CUDA-on for MSVC (GPU lanes unchanged). A developer may pass
# -DGGML_CUDA=OFF to get a fast CPU-only dev build (a full CUDA build of
# llama.cpp takes 60+ min); in that case honor the explicit OFF instead of
# forcing it back ON. Only force the MSVC default when GGML_CUDA was not set.
if(MSVC)
    if(NOT DEFINED GGML_CUDA)
        set(GGML_CUDA ON CACHE BOOL "" FORCE)
    endif()
    if(GGML_CUDA AND NOT DEFINED CMAKE_CUDA_ARCHITECTURES)
        set(CMAKE_CUDA_ARCHITECTURES 89 CACHE STRING "" FORCE)
    endif()
else()
    set(GGML_CUDA OFF CACHE BOOL "" FORCE)
endif()

FetchContent_Declare(llamacpp
    URL https://github.com/ggml-org/llama.cpp/archive/refs/tags/${AQUILA_LLAMACPP_TAG}.tar.gz
    URL_HASH SHA256=a73304d879523eed3e656176116b9191b5cd0b6603ded4657814de5c0c9a45f5
    SYSTEM EXCLUDE_FROM_ALL)

# Build the upstream tree at ITS native C++ standard (17), not Aquila's C++20.
# llama.cpp/ggml use u8"..." string literals that, under MSVC + C++20, become
# `char8_t[]` and no longer convert to `const char*` (e.g. src/llama-chat.cpp),
# breaking the upstream build. llama.cpp does not set its own CXX_STANDARD, so it
# inherits our global C++20; pin it to 17 across the FetchContent subtree, then
# restore so Aquila's own TUs keep compiling as C++20. (Our wrapper TUs live in
# aquila_core, outside this subtree, and are unaffected.)
set(_aq_saved_cxx_standard "${CMAKE_CXX_STANDARD}")
set(CMAKE_CXX_STANDARD 17)
FetchContent_MakeAvailable(llamacpp)
set(CMAKE_CXX_STANDARD "${_aq_saved_cxx_standard}")

# Scope OUR flags OUT of the upstream targets: they must NOT see Aquila's
# -fsanitize / -Werror / /WX. SYSTEM includes above keep their headers quiet; the
# precedent for per-target flag scoping is cmake/AquilaTreeSitter.cmake. We set
# the sanitizer-scrub as a per-target compile/link option override. Our own
# wrapper TUs stay instrumented, so the sanitizer still covers M5's own code.
if(AQUILA_SANITIZE AND NOT MSVC)
    # Build the sanitizer spec the same way AquilaSanitizers.cmake does, to turn
    # each one OFF on the upstream targets.
    set(_aq_llama_noscan "")
    foreach(_san IN LISTS AQUILA_SANITIZE)
        list(APPEND _aq_llama_noscan "-fno-sanitize=${_san}")
    endforeach()
    foreach(_tgt llama ggml llama-common llama-common-base)
        if(TARGET ${_tgt})
            target_compile_options(${_tgt} PRIVATE ${_aq_llama_noscan})
        endif()
    endforeach()
endif()

# Public link surface: `llama` transitively pulls ggml; `llama-common` carries
# json_schema_to_grammar. Guard against a target-name drift between tags.
set(_aq_llama_libs "")
foreach(_tgt llama llama-common)
    if(TARGET ${_tgt})
        list(APPEND _aq_llama_libs ${_tgt})
    endif()
endforeach()

target_compile_definitions(aquila_llamacpp INTERFACE AQUILA_HAS_LLAMACPP=1)
target_link_libraries(aquila_llamacpp INTERFACE ${_aq_llama_libs})
# `llama.h` is under include/; the common headers (json-schema-to-grammar.h) under
# common/. Expose both as SYSTEM so our /W4 /WX and -Werror never see them.
target_include_directories(aquila_llamacpp SYSTEM INTERFACE
    "${llamacpp_SOURCE_DIR}/include"
    "${llamacpp_SOURCE_DIR}/common"
    "${llamacpp_SOURCE_DIR}/ggml/include")

# --- tiny real-weight test model (CI-safe fast decode) ----------------------
# A ~19 MB stories15M (Llama2 15M, q4_0) GGUF, pinned by URL + SHA256 like every
# other dependency. It gives the backend unit tests a REAL model to decode against
# that is small enough to run in CI, instead of skipping (the 9B Qwen is reserved
# for the opt-in GPU/live proofs). Fetched only when AQUILA_LLAMACPP is ON; the
# path is exposed as AQUILA_TINY_GGUF_PATH for tests/unit/CMakeLists.txt to inject
# as the AQUILA_TINY_GGUF compile definition. The tests still SKIP gracefully if the
# file is somehow absent, so a fetch failure never turns into a hard test failure.
set(_aq_tiny_gguf_sha256 66967fbece6dbe97886593fdbb73589584927e29119ec31f08090732d1861739)
FetchContent_Declare(aquila_tiny_gguf
    URL https://huggingface.co/ggml-org/models/resolve/main/tinyllamas/stories15M-q4_0.gguf
    URL_HASH SHA256=${_aq_tiny_gguf_sha256}
    DOWNLOAD_NO_EXTRACT TRUE)
FetchContent_MakeAvailable(aquila_tiny_gguf)
# The downloaded file keeps its URL basename under the fetch content dir.
set(AQUILA_TINY_GGUF_PATH "${aquila_tiny_gguf_SOURCE_DIR}/stories15M-q4_0.gguf"
    CACHE INTERNAL "Path to the tiny test GGUF fetched for the unit tests")

# --- Qwen 3.5 4B Q4_K_M, the bake-off deciding model (M5 task 11, Req 9 / D14) ---
# ~2.75 GB, so it is OPT-IN: fetched only when AQUILA_LIVE_TESTS is ON (the bake-off
# is a live test, out of CI). Pinned by URL + SHA256 like every other model/dep for
# reproducibility. A local copy next to the 9B is preferred when present (same as
# the 9B's default path), so a developer who already has it does not re-download.
# Exposed as AQUILA_BAKEOFF_GGUF_4B_PATH for tests/live/CMakeLists.txt.
#   unsloth/Qwen3.5-4B-GGUF, arch qwen35 (same recurrent/M-RoPE family as the 9B),
#   Apache-2.0. This is the CPU-first deciding lane; the 9B (GPU) only confirms.
if(AQUILA_LIVE_TESTS)
    set(_aq_local_4b "F:/Users/myfri/agent-projects/Qwen3.5-4B-Q4_K_M.gguf")
    if(EXISTS "${_aq_local_4b}")
        set(AQUILA_BAKEOFF_GGUF_4B_PATH "${_aq_local_4b}"
            CACHE INTERNAL "Path to the bake-off Qwen 3.5 4B GGUF (local copy)")
        message(STATUS "Aquila bake-off: using local Qwen 3.5 4B at ${_aq_local_4b}")
    else()
        set(_aq_4b_sha256 bf37767fa8d89ec3ba0ad3d614301f2f6fcb8b49360bc562502955543deb001d)
        FetchContent_Declare(aquila_qwen4b_gguf
            URL https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf
            URL_HASH SHA256=${_aq_4b_sha256}
            DOWNLOAD_NO_EXTRACT TRUE)
        FetchContent_MakeAvailable(aquila_qwen4b_gguf)
        set(AQUILA_BAKEOFF_GGUF_4B_PATH
            "${aquila_qwen4b_gguf_SOURCE_DIR}/Qwen3.5-4B-Q4_K_M.gguf"
            CACHE INTERNAL "Path to the bake-off Qwen 3.5 4B GGUF (fetched)")
    endif()

# --- Base model pair (D15, R18): Llama 3.2 3B (CPU) + Llama 3.1 8B (GPU) --------
# Ratified from the section-8.5 F3 model-family bake-off: Llama 3.2 3B does GBNF
# actions cleanly where Qwen 3.5 4B degenerates (F2). Plain-RoPE (arch llama), so no
# M-RoPE rollback hazard. bartowski Q4_K_M, pinned by SHA256. Local copies on D: are
# preferred when present; exposed as AQUILA_BASE_GGUF_3B_PATH / _8B_PATH.
if(AQUILA_LIVE_TESTS)
    set(_aq_llama3b "D:/aquila-models/Llama-3.2-3B-Instruct-Q4_K_M.gguf")
    if(EXISTS "${_aq_llama3b}")
        set(AQUILA_BASE_GGUF_3B_PATH "${_aq_llama3b}" CACHE INTERNAL "Llama 3.2 3B base model (local)")
    else()
        FetchContent_Declare(aquila_llama3b_gguf
            URL https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf
            URL_HASH SHA256=6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff
            DOWNLOAD_NO_EXTRACT TRUE)
        FetchContent_MakeAvailable(aquila_llama3b_gguf)
        set(AQUILA_BASE_GGUF_3B_PATH "${aquila_llama3b_gguf_SOURCE_DIR}/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
            CACHE INTERNAL "Llama 3.2 3B base model (fetched)")
    endif()

    set(_aq_llama8b "D:/aquila-models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf")
    if(EXISTS "${_aq_llama8b}")
        set(AQUILA_BASE_GGUF_8B_PATH "${_aq_llama8b}" CACHE INTERNAL "Llama 3.1 8B base model (local)")
    else()
        FetchContent_Declare(aquila_llama8b_gguf
            URL https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
            URL_HASH SHA256=7b064f5842bf9532c91456deda288a1b672397a54fa729aa665952863033557c
            DOWNLOAD_NO_EXTRACT TRUE)
        FetchContent_MakeAvailable(aquila_llama8b_gguf)
        set(AQUILA_BASE_GGUF_8B_PATH "${aquila_llama8b_gguf_SOURCE_DIR}/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
            CACHE INTERNAL "Llama 3.1 8B base model (fetched)")
    endif()
    message(STATUS "Aquila base models (D15): 3B=${AQUILA_BASE_GGUF_3B_PATH} 8B=${AQUILA_BASE_GGUF_8B_PATH}")
endif()

endif()
