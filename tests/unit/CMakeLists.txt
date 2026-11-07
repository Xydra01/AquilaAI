add_executable(aquila_unit_tests
    deps_probe_test.cpp
    types_roundtrip_test.cpp
    types_errors_test.cpp
    recipe_doc_test.cpp
    mutation_robustness_test.cpp
    ollama_wire_test.cpp
    ollama_backend_test.cpp
    syntax_test.cpp
    registry_test.cpp
    path_firewall_test.cpp
    diff_test.cpp
    canvas_buffer_test.cpp
    workspace_module_test.cpp
    python_oracle_test.cpp
    process_test.cpp
    diagnostics_test.cpp
    execution_module_test.cpp
    runtime_tier_test.cpp
    run_record_test.cpp
    context_condenser_test.cpp
    orchestrator_module_test.cpp
    agent_loop_test.cpp
    recipe_cartridge_test.cpp
    # M5 (tasks 2.3/2.4): LlamaSession checkpoint/rollback properties + RAII/overflow
    # unit tests. The whole llama-dependent body is guarded by `#if AQUILA_HAS_LLAMACPP`,
    # so on the stub lanes (mingw-san / msvc-asan) it compiles to one trivially-passing
    # TEST_CASE. The AQUILA_HAS_LLAMACPP macro reaches this TU via the aquila_llamacpp
    # INTERFACE link added below (aquila_core links it PRIVATE, so it does NOT propagate
    # through aquila::core -- the test target must link it directly for the guard).
    llama_session_test.cpp
    # M5 (task 3.2): GrammarFactory schema->GBNF + typed grammar-failure (Property 5).
    # Same AQUILA_HAS_LLAMACPP guard + tiny-GGUF SKIP pattern as llama_session_test.cpp;
    # the pure gbnf_for cases run with no model, the vocab-backed sampler cases skip
    # when AQUILA_TINY_GGUF is absent.
    grammar_test.cpp
    # M5 (tasks 4.3/4.4): LlamaCppBackend generate() properties (GBNF-always-parses,
    # KV-unchanged, cancellation, prefix-reuse) + streaming/EOS/error-vocabulary unit
    # tests. Same `#if AQUILA_HAS_LLAMACPP` guard + AQUILA_TINY_GGUF SKIP pattern as
    # llama_session_test.cpp: one trivially-passing TEST_CASE on the stub lanes.
    llama_backend_test.cpp
    sqlite_db_test.cpp
    fact_store_test.cpp
    embedding_test.cpp
    vector_index_test.cpp
    html_cleaner_test.cpp
    page_cache_test.cpp
    document_chunker_test.cpp
    page_scorer_test.cpp
    web_search_test.cpp
    knowledge_module_test.cpp
    knowledge_recipe_test.cpp
    document_module_test.cpp
    persona_module_test.cpp
    learn_module_test.cpp
    script_module_test.cpp
    recipe_nesting_test.cpp
    micro_pass_test.cpp
    recipes_all_test.cpp
    cli_test.cpp)
target_link_libraries(aquila_unit_tests PRIVATE
    aquila::core aquila_cli_lib httplib::httplib Catch2::Catch2WithMain rapidcheck_catch
    # Carries AQUILA_HAS_LLAMACPP (1 built / 0 stubbed) into this test TU so the
    # llama_session_test.cpp guard resolves; when built it also brings the llama.cpp
    # SYSTEM includes so the test can query <llama.h> (llama_memory_seq_pos_max).
    aquila_llamacpp)
target_compile_definitions(aquila_unit_tests PRIVATE
    AQUILA_FIXTURE_DIR="${PROJECT_SOURCE_DIR}/tests/fixtures"
    AQUILA_RECIPE_DIR="${PROJECT_SOURCE_DIR}/src/core/agent/recipes"
    AQUILA_DESIGN_DOC="${PROJECT_SOURCE_DIR}/docs/design/aquila-cpp-design.md"
    AQUILA_PROC_HELPER="$<TARGET_FILE:aquila_proc_helper>"
    # M5 CI-SAFE MODEL FIXTURE (tasks 2.3/2.4; the pattern tasks 3.2/4.3/4.4 reuse):
    # absolute path (forward slashes) to a tiny real-weight GGUF cached OUTSIDE the
    # source tree (stories15M, a Llama2 15M q4_0). It is a LOCAL CACHE, not pinned
    # via FetchContent yet, so the tests SKIP gracefully when the file is absent (CI
    # on a machine without it, and the stub lanes, stay green). FOLLOW-UP: pin the
    # model (URL + SHA256 FetchContent) so CI can fetch it -- orchestrator decision.
    AQUILA_TINY_GGUF="${AQUILA_TINY_GGUF_PATH}")
add_dependencies(aquila_unit_tests aquila_proc_helper)
aquila_set_warnings(aquila_unit_tests)

add_test(NAME unit COMMAND aquila_unit_tests --reporter console)
aquila_test_env(unit)
