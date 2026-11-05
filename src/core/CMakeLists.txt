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
    # M5: always listed; the TU is wrapped in `#if AQUILA_HAS_LLAMACPP` so it
    # compiles to an empty object on stub lanes (mingw-san / msvc-asan) and to the
    # real LlamaSession where the backend is built. The llama.cpp link libs +
    # SYSTEM includes arrive via the `aquila_llamacpp` INTERFACE target below.
    inference/llama_session.cpp
    # M5 (task 3.1): same guard as llama_session.cpp -- the whole TU is wrapped in
    # `#if AQUILA_HAS_LLAMACPP`, so it is an empty object on stub lanes and the real
    # GrammarFactory (schema -> GBNF via llama.cpp's common lib) where built.
    inference/grammar.cpp
    # M5 (task 4.1): same guard as llama_session.cpp / grammar.cpp -- the whole TU
    # is wrapped in `#if AQUILA_HAS_LLAMACPP`, so it is an empty object on stub lanes
    # and the real LlamaCppBackend (IInferenceBackend over LlamaSession + GBNF) where
    # built. generate's token loop is task 4.2; 4.1 ships a compiling stub.
    inference/llama_backend.cpp
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
    modules/builtin.cpp
    agent/runtime_tier.cpp
    agent/run_record.cpp
    agent/context_condenser.cpp
    agent/orchestrator_module.cpp
    agent/agent_loop.cpp)
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
        tree_sitter_python
        # M5: carries AQUILA_HAS_LLAMACPP (1 built / 0 stubbed) and, when built, the
        # llama.cpp link libs + SYSTEM includes. No backend source exists yet, so
        # this only defines the macro today; task 2.1 adds the backend TUs guarded
        # by `#if AQUILA_HAS_LLAMACPP`. Linking an INTERFACE target compiles nothing
        # at configure time; on stub lanes it never pulls in llama.cpp.
        aquila_llamacpp)
aquila_set_warnings(aquila_core)
