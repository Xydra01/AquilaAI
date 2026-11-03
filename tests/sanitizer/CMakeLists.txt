# Defects are deliberate, so the strict warning set is not applied to this target.
add_executable(aquila_defects defects.cpp)

function(aquila_defect_test name mode regex)
    add_test(NAME sanitizer.${name} COMMAND aquila_defects ${mode})
    set_tests_properties(sanitizer.${name} PROPERTIES
        PASS_REGULAR_EXPRESSION "${regex}"
        LABELS sanitizer)
    aquila_test_env(sanitizer.${name})
endfunction()

# Control: a clean run must exit 0 and print no sanitizer or leak report.
add_test(NAME sanitizer.none COMMAND aquila_defects none)
set_tests_properties(sanitizer.none PROPERTIES
    FAIL_REGULAR_EXPRESSION "Sanitizer|runtime error|memory leaks"
    LABELS sanitizer)
aquila_test_env(sanitizer.none)

if(AQUILA_ASAN)
    aquila_defect_test(report report "asan=1")
    aquila_defect_test(heap_overflow heap_overflow "AddressSanitizer: heap-buffer-overflow")
    aquila_defect_test(use_after_free use_after_free "AddressSanitizer: heap-use-after-free")
else()
    # Negative control: a non-ASan build must not be instrumented.
    aquila_defect_test(report report "asan=0")
endif()

if(AQUILA_UBSAN)
    aquila_defect_test(signed_overflow signed_overflow "runtime error: signed integer overflow")
endif()

if(AQUILA_ASAN AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
    aquila_defect_test(leak leak "LeakSanitizer: detected memory leaks")
    set_property(TEST sanitizer.leak APPEND PROPERTY ENVIRONMENT "ASAN_OPTIONS=detect_leaks=1")
elseif(MSVC AND CMAKE_BUILD_TYPE STREQUAL "Debug")
    # MSVC ASan replaces the allocator, which disables the CRT debug heap's leak
    # report, and MSVC has no LeakSanitizer. Leaks are checked by a non-ASan build
    # of the same source.
    add_executable(aquila_defects_crt defects.cpp)
    get_target_property(_opts aquila_defects_crt COMPILE_OPTIONS)
    if(_opts)
        list(FILTER _opts EXCLUDE REGEX "fsanitize")
        set_target_properties(aquila_defects_crt PROPERTIES COMPILE_OPTIONS "${_opts}")
    endif()

    add_test(NAME sanitizer.crt_none COMMAND aquila_defects_crt none)
    set_tests_properties(sanitizer.crt_none PROPERTIES
        FAIL_REGULAR_EXPRESSION "memory leaks"
        LABELS sanitizer)

    add_test(NAME sanitizer.crt_report COMMAND aquila_defects_crt report)
    set_tests_properties(sanitizer.crt_report PROPERTIES
        PASS_REGULAR_EXPRESSION "asan=0"
        LABELS sanitizer)

    add_test(NAME sanitizer.crt_leak COMMAND aquila_defects_crt leak)
    set_tests_properties(sanitizer.crt_leak PROPERTIES
        PASS_REGULAR_EXPRESSION "Detected memory leaks!"
        LABELS sanitizer)
endif()
