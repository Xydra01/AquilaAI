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
    target_compile_definitions(aquila_llamacpp INTERFACE AQUILA_HAS_LLAMACPP=0 AQUILA_HAS_MTMD=0)
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
set(LLAMA_BUILD_MTMD     ON  CACHE BOOL "" FORCE)
set(MTMD_VIDEO           OFF CACHE BOOL "" FORCE)
set(GGML_BUILD_TESTS     OFF CACHE BOOL "" FORCE)
set(GGML_BUILD_EXAMPLES  OFF CACHE BOOL "" FORCE)
# We link llama.cpp statically into aquila_core; a shared ggml/llama would need its
# DLLs on PATH for the tests. Static keeps the test exes self-contained.
set(BUILD_SHARED_LIBS    OFF CACHE BOOL "" FORCE)

# GPU is OPT-IN, not a blanket MSVC default (H12). CUDA requires the MSVC host
# compiler AND the CUDA toolkit; CI's plain msvc-release runner has neither, so
# forcing CUDA on for every MSVC build broke CI (ggml-cuda CMakeLists errors with no
# toolkit). CUDA is enabled only when the build asks for it via AQUILA_ENABLE_CUDA
# (the msvc-release-cuda preset sets it), and only on MSVC. An explicit -DGGML_CUDA
# always wins (lets a dev force CPU-only or CUDA directly). sm_89 = RTX 4070.
option(AQUILA_ENABLE_CUDA "Build llama.cpp with the CUDA backend (MSVC only)" OFF)
if(NOT DEFINED GGML_CUDA)
    if(MSVC AND AQUILA_ENABLE_CUDA)
        set(GGML_CUDA ON CACHE BOOL "" FORCE)
    else()
        set(GGML_CUDA OFF CACHE BOOL "" FORCE)
    endif()
endif()
if(GGML_CUDA AND NOT DEFINED CMAKE_CUDA_ARCHITECTURES)
    set(CMAKE_CUDA_ARCHITECTURES 89 CACHE STRING "" FORCE)
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
    # Turn our sanitizers OFF on EVERY upstream llama.cpp/ggml target, not a hardcoded
    # few. We test our wrapper, not ggml's internals. The compute kernels live in ggml
    # SUB-targets (ggml-base, ggml-cpu, ...), and ggml dispatches quantize/dequantize
    # through function pointers whose static type differs from the callee -- which
    # UBSan's -fsanitize=function flags as undefined behavior at RUNTIME when the
    # llamacpp unit tests decode on the tiny model (ggml-cpu/ops.cpp dequantize_row_*).
    # This is the same upstream pattern tree-sitter needed -fsanitize=function off for.
    # Collect ALL targets defined under the llamacpp subtree and scrub each.
    set(_aq_llama_noscan "")
    foreach(_san IN LISTS AQUILA_SANITIZE)
        list(APPEND _aq_llama_noscan "-fno-sanitize=${_san}")
    endforeach()
    # -fsanitize=function is enabled as part of -fsanitize=undefined but must be named
    # explicitly to be sure it is disabled on these targets (it is the one that fires).
    list(APPEND _aq_llama_noscan "-fno-sanitize=function")

    # Recursively collect EVERY target under the llamacpp subtree and scrub each, so
    # no ggml sub-target (ggml-base, ggml-cpu and its arch variants, vendored libs)
    # is missed regardless of upstream target-name changes between tags.
    set(_aq_scan_dirs "${llamacpp_SOURCE_DIR}")
    set(_aq_llama_all_tgts "")
    while(_aq_scan_dirs)
        list(POP_FRONT _aq_scan_dirs _aq_dir)
        get_property(_aq_dtgts DIRECTORY "${_aq_dir}" PROPERTY BUILDSYSTEM_TARGETS)
        list(APPEND _aq_llama_all_tgts ${_aq_dtgts})
        get_property(_aq_subdirs DIRECTORY "${_aq_dir}" PROPERTY SUBDIRECTORIES)
        list(APPEND _aq_scan_dirs ${_aq_subdirs})
    endwhile()
    foreach(_tgt IN LISTS _aq_llama_all_tgts)
        get_target_property(_aq_ttype ${_tgt} TYPE)
        if(NOT _aq_ttype STREQUAL "INTERFACE_LIBRARY" AND NOT _aq_ttype STREQUAL "UTILITY")
            target_compile_options(${_tgt} PRIVATE ${_aq_llama_noscan})
        endif()
    endforeach()
endif()

# Public link surface: `llama` transitively pulls ggml; `llama-common` carries
# json_schema_to_grammar + common_chat_templates; `mtmd` carries multimodal vision.
set(_aq_llama_libs "")
foreach(_tgt llama llama-common mtmd)
    if(TARGET ${_tgt})
        list(APPEND _aq_llama_libs ${_tgt})
    endif()
endforeach()

target_compile_definitions(aquila_llamacpp INTERFACE AQUILA_HAS_LLAMACPP=1)
if(TARGET mtmd)
    target_compile_definitions(aquila_llamacpp INTERFACE AQUILA_HAS_MTMD=1)
else()
    target_compile_definitions(aquila_llamacpp INTERFACE AQUILA_HAS_MTMD=0)
endif()
target_link_libraries(aquila_llamacpp INTERFACE ${_aq_llama_libs})
# `llama.h` is under include/; the common headers under common/; mtmd headers under
# tools/mtmd/. Expose as SYSTEM so our /W4 /WX and -Werror never see them.
target_include_directories(aquila_llamacpp SYSTEM INTERFACE
    "${llamacpp_SOURCE_DIR}/include"
    "${llamacpp_SOURCE_DIR}/common"
    "${llamacpp_SOURCE_DIR}/tools/mtmd"
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

# --- Qwen 3.5 Model Family (4B CPU default + 9B GPU + mmproj vision) -----------
# Pinned by URL + SHA256 when AQUILA_LIVE_TESTS is ON (out of normal CI). Local
# copies under F:/Users/myfri/agent-projects or LM Studio are preferred when present.
if(AQUILA_LIVE_TESTS)
    set(_aq_f_4b "F:/aquila-models/Qwen3.5-4B-Q4_K_M.gguf")
    set(_aq_local_4b "F:/Users/myfri/agent-projects/Qwen3.5-4B-Q4_K_M.gguf")
    if(EXISTS "${_aq_f_4b}")
        set(AQUILA_BAKEOFF_GGUF_4B_PATH "${_aq_f_4b}"
            CACHE INTERNAL "Path to Qwen 3.5 4B GGUF (F:/aquila-models copy)")
        message(STATUS "Aquila Qwen 3.5 4B: using ${_aq_f_4b}")
    elseif(EXISTS "${_aq_local_4b}")
        set(AQUILA_BAKEOFF_GGUF_4B_PATH "${_aq_local_4b}"
            CACHE INTERNAL "Path to Qwen 3.5 4B GGUF (local copy)")
        message(STATUS "Aquila Qwen 3.5 4B: using local ${_aq_local_4b}")
    else()
        set(_aq_4b_sha256 00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4)
        FetchContent_Declare(aquila_qwen4b_gguf
            URL https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf
            URL_HASH SHA256=${_aq_4b_sha256}
            DOWNLOAD_NO_EXTRACT TRUE)
        FetchContent_MakeAvailable(aquila_qwen4b_gguf)
        set(AQUILA_BAKEOFF_GGUF_4B_PATH
            "${aquila_qwen4b_gguf_SOURCE_DIR}/Qwen3.5-4B-Q4_K_M.gguf"
            CACHE INTERNAL "Path to Qwen 3.5 4B GGUF (fetched)")
    endif()

    set(_aq_f_4b_mmproj "F:/aquila-models/mmproj-Qwen3.5-4B-F16.gguf")
    set(_aq_local_4b_mmproj "F:/Users/myfri/agent-projects/mmproj-Qwen3.5-4B-F16.gguf")
    if(EXISTS "${_aq_f_4b_mmproj}")
        set(AQUILA_QWEN_4B_MMPROJ_PATH "${_aq_f_4b_mmproj}"
            CACHE INTERNAL "Path to Qwen 3.5 4B mmproj GGUF (F:/aquila-models copy)")
    elseif(EXISTS "${_aq_local_4b_mmproj}")
        set(AQUILA_QWEN_4B_MMPROJ_PATH "${_aq_local_4b_mmproj}"
            CACHE INTERNAL "Path to Qwen 3.5 4B mmproj GGUF (local copy)")
    else()
        FetchContent_Declare(aquila_qwen4b_mmproj
            URL https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/mmproj-F16.gguf
            URL_HASH SHA256=cd88edcf8d031894960bb0c9c5b9b7e1fea6ebee02b9f7ce925a00d12891f864
            DOWNLOAD_NO_EXTRACT TRUE)
        FetchContent_MakeAvailable(aquila_qwen4b_mmproj)
        set(AQUILA_QWEN_4B_MMPROJ_PATH "${aquila_qwen4b_mmproj_SOURCE_DIR}/mmproj-F16.gguf"
            CACHE INTERNAL "Path to Qwen 3.5 4B mmproj GGUF (fetched)")
    endif()

    set(_aq_f_9b "F:/aquila-models/Qwen3.5-9B-Q4_K_M.gguf")
    set(_aq_local_9b "F:/Users/myfri/agent-projects/Qwen3.5-9B-Q4_K_M.gguf")
    set(_aq_lms_9b "F:/Users/myfri/.lmstudio/models/lmstudio-community/Qwen3.5-9B-GGUF/Qwen3.5-9B-Q4_K_M.gguf")
    if(EXISTS "${_aq_f_9b}")
        set(AQUILA_BASE_GGUF_9B_PATH "${_aq_f_9b}"
            CACHE INTERNAL "Path to Qwen 3.5 9B GGUF (F:/aquila-models copy)")
        message(STATUS "Aquila Qwen 3.5 9B: using ${_aq_f_9b}")
    elseif(EXISTS "${_aq_local_9b}")
        set(AQUILA_BASE_GGUF_9B_PATH "${_aq_local_9b}"
            CACHE INTERNAL "Path to Qwen 3.5 9B GGUF (local copy)")
    elseif(EXISTS "${_aq_lms_9b}")
        set(AQUILA_BASE_GGUF_9B_PATH "${_aq_lms_9b}"
            CACHE INTERNAL "Path to Qwen 3.5 9B GGUF (LM Studio local copy)")
    else()
        FetchContent_Declare(aquila_qwen9b_gguf
            URL https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf
            URL_HASH SHA256=03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8
            DOWNLOAD_NO_EXTRACT TRUE)
        FetchContent_MakeAvailable(aquila_qwen9b_gguf)
        set(AQUILA_BASE_GGUF_9B_PATH "${aquila_qwen9b_gguf_SOURCE_DIR}/Qwen3.5-9B-Q4_K_M.gguf"
            CACHE INTERNAL "Path to Qwen 3.5 9B GGUF (fetched)")
    endif()

    set(_aq_f_9b_mmproj "F:/aquila-models/mmproj-Qwen3.5-9B-BF16.gguf")
    set(_aq_lms_9b_mmproj "F:/Users/myfri/.lmstudio/models/lmstudio-community/Qwen3.5-9B-GGUF/mmproj-Qwen3.5-9B-BF16.gguf")
    set(_aq_local_9b_mmproj "F:/Users/myfri/agent-projects/mmproj-Qwen3.5-9B-BF16.gguf")
    if(EXISTS "${_aq_f_9b_mmproj}")
        set(AQUILA_QWEN_9B_MMPROJ_PATH "${_aq_f_9b_mmproj}"
            CACHE INTERNAL "Path to Qwen 3.5 9B mmproj GGUF (F:/aquila-models copy)")
    elseif(EXISTS "${_aq_lms_9b_mmproj}")
        set(AQUILA_QWEN_9B_MMPROJ_PATH "${_aq_lms_9b_mmproj}"
            CACHE INTERNAL "Path to Qwen 3.5 9B mmproj GGUF (LM Studio local copy)")
    elseif(EXISTS "${_aq_local_9b_mmproj}")
        set(AQUILA_QWEN_9B_MMPROJ_PATH "${_aq_local_9b_mmproj}"
            CACHE INTERNAL "Path to Qwen 3.5 9B mmproj GGUF (local copy)")
    else()
        FetchContent_Declare(aquila_qwen9b_mmproj
            URL https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/mmproj-BF16.gguf
            URL_HASH SHA256=853698ce7aa6c7ba732478bad280240969ddf7b0fcbf93900046f63903a83383
            DOWNLOAD_NO_EXTRACT TRUE)
        FetchContent_MakeAvailable(aquila_qwen9b_mmproj)
        set(AQUILA_QWEN_9B_MMPROJ_PATH "${aquila_qwen9b_mmproj_SOURCE_DIR}/mmproj-BF16.gguf"
            CACHE INTERNAL "Path to Qwen 3.5 9B mmproj GGUF (fetched)")
    endif()

    set(AQUILA_BASE_GGUF_4B_PATH "${AQUILA_BAKEOFF_GGUF_4B_PATH}" CACHE INTERNAL "Qwen 3.5 4B default model")
    message(STATUS "Aquila Qwen 3.5 models: 4B=${AQUILA_BASE_GGUF_4B_PATH} 9B=${AQUILA_BASE_GGUF_9B_PATH}")
endif()
