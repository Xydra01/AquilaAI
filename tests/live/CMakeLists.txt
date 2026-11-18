add_executable(aquila_live_tests
    ollama_live_test.cpp
    agent_loop_live_test.cpp
    llama_backend_live_test.cpp
    # M5 task 11.3/11.4 (Req 9 / D14): the context-strategy bake-off harness. Guarded
    # by `#if AQUILA_HAS_LLAMACPP`; skips when the bake-off model is absent.
    context_bakeoff_live_test.cpp
    # M5 task 6.1 (Req 8.4): Ollama<->llama.cpp parity cross-check (same Qwen 3.5 family).
    parity_live_test.cpp)
target_link_libraries(aquila_live_tests PRIVATE
    aquila::core httplib::httplib Catch2::Catch2WithMain aquila_llamacpp)
if(TARGET aquila_browser)
    target_compile_definitions(aquila_live_tests PRIVATE AQUILA_HAS_BROWSER=1)
    add_dependencies(aquila_live_tests aquila_browser)
endif()
aquila_set_warnings(aquila_live_tests)

# Inject the pinned Qwen 3.5 4B path (set by cmake/AquilaLlamaCpp.cmake when
# AQUILA_LIVE_TESTS is ON). The bake-off defaults to this CPU deciding model; an
# env override (AQUILA_BAKEOFF_GGUF / AQUILA_BAKEOFF_GPU) selects the 9B GPU
# confirmation lane at run time.
if(DEFINED AQUILA_BAKEOFF_GGUF_4B_PATH)
    target_compile_definitions(aquila_live_tests PRIVATE
        AQUILA_BAKEOFF_GGUF_4B="${AQUILA_BAKEOFF_GGUF_4B_PATH}")
endif()

# Ollama HTTP & agent loop live tests (exclude in-process llama.cpp CUDA tests
# so Ollama's resident weights and an in-process 9B GGUF do not overlap).
add_test(NAME live.ollama COMMAND aquila_live_tests "~[llama_backend_live]~[context_bakeoff]~[parity]" --reporter console)
set_tests_properties(live.ollama PROPERTIES LABELS live)
aquila_test_env(live.ollama)

# Direct in-process llama.cpp GPU + multimodal + hybrid snapshot tests.
add_test(NAME live.llama_backend COMMAND aquila_live_tests "[llama_backend_live]" --reporter console)
set_tests_properties(live.llama_backend PROPERTIES LABELS live)
if(DEFINED AQUILA_QT_BIN_DIR)
    aquila_test_env(live.llama_backend "${AQUILA_QT_BIN_DIR}")
else()
    aquila_test_env(live.llama_backend)
endif()

# A separate ctest that runs ONLY the bake-off tag, so D14 can be decided without
# the long Ollama live run. Same `live` label (excluded from CI).
add_test(NAME live.bakeoff COMMAND aquila_live_tests "[context_bakeoff]" --reporter console)
set_tests_properties(live.bakeoff PROPERTIES LABELS live)
aquila_test_env(live.bakeoff)

add_test(NAME live.parity COMMAND aquila_live_tests "[parity]" --reporter console)
set_tests_properties(live.parity PROPERTIES LABELS live)
aquila_test_env(live.parity)