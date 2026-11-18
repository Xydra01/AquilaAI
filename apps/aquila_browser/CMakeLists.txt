qt_standard_project_setup()

qt_add_executable(aquila_browser
    main.cpp
    browser_session.hpp
    browser_session.cpp
)

target_link_libraries(aquila_browser PRIVATE
    Qt6::Widgets
    Qt6::Network
    Qt6::WebEngineWidgets
)
target_compile_definitions(aquila_browser PRIVATE
    AQUILA_DEFAULT_SEARXNG_SCRIPT="${CMAKE_SOURCE_DIR}/scripts/run_searxng.py"
)
aquila_set_warnings(aquila_browser)

if(WIN32 AND TARGET Qt6::qmake)
    get_target_property(_qmake Qt6::qmake IMPORTED_LOCATION)
    get_filename_component(_qt_bin_dir "${_qmake}" DIRECTORY)
    find_program(WINDEPLOYQT_EXECUTABLE windeployqt HINTS "${_qt_bin_dir}")
    if(WINDEPLOYQT_EXECUTABLE)
        add_custom_command(TARGET aquila_browser POST_BUILD
            COMMAND "${WINDEPLOYQT_EXECUTABLE}" --no-translations --no-compiler-runtime "$<TARGET_FILE:aquila_browser>"
            COMMENT "Deploying Qt dependencies for aquila_browser..."
        )
    endif()
endif()

add_test(NAME browser.smoke COMMAND aquila_browser --smoke "${CMAKE_CURRENT_BINARY_DIR}/smoke_out")
set_tests_properties(browser.smoke PROPERTIES
    PASS_REGULAR_EXPRESSION "\\[BROWSER-SMOKE-OK\\]"
    TIMEOUT 60)
if(NOT WIN32)
    set_property(TEST browser.smoke PROPERTY ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()
aquila_test_env(browser.smoke "${AQUILA_QT_BIN_DIR}")
