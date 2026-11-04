add_executable(aquila_live_tests ollama_live_test.cpp agent_loop_live_test.cpp)
target_link_libraries(aquila_live_tests PRIVATE aquila::core httplib::httplib Catch2::Catch2WithMain)
aquila_set_warnings(aquila_live_tests)

add_test(NAME live.ollama COMMAND aquila_live_tests --reporter console)
set_tests_properties(live.ollama PROPERTIES LABELS live)
aquila_test_env(live.ollama)
