find_package(Qt6 6.11 QUIET COMPONENTS Widgets OpenGL OpenGLWidgets)
if(NOT Qt6_FOUND)
    message(FATAL_ERROR
        "Qt6 (>= 6.11, Widgets) not found. Set QT_ROOT_DIR to the Qt MSVC kit, e.g. "
        "F:\\Qt\\6.11.3\\msvc2022_64 (install with scripts/install-qt.ps1), "
        "or configure with -DAQUILA_BUILD_GUI=OFF.")
endif()
message(STATUS "Qt6 Widgets ${Qt6_VERSION}: ${Qt6_DIR}")

if(AQUILA_REQUIRE_WEBENGINE)
    find_package(Qt6 REQUIRED COMPONENTS WebEngineWidgets)
    message(STATUS "Qt6 WebEngineWidgets ${Qt6WebEngineWidgets_VERSION}: ${Qt6WebEngineWidgets_DIR}")
endif()

qt_standard_project_setup()

qt_add_executable(aquila_gui
    main.cpp
    main_window.hpp
    main_window.cpp
    theme/theme.hpp
    theme/theme.cpp
    theme/markdown_renderer.hpp
    theme/markdown_renderer.cpp
    widgets/nav_rail.hpp
    widgets/nav_rail.cpp
    widgets/flow_layout.hpp
    widgets/flow_layout.cpp
    widgets/code_editor.hpp
    widgets/code_editor.cpp
    widgets/inline_prompt_bar.hpp
    widgets/inline_prompt_bar.cpp
    widgets/inline_diff_overlay.hpp
    widgets/inline_diff_overlay.cpp
    widgets/pending_patch_widget.hpp
    widgets/pending_patch_widget.cpp
    worker/agent_worker.hpp
    worker/agent_worker.cpp
    pages/base_page.hpp
    pages/base_page.cpp
    pages/home_page.hpp
    pages/home_page.cpp
    pages/chat_page.hpp
    pages/chat_page.cpp
    pages/task_page.hpp
    pages/task_page.cpp
    pages/code_ide_page.hpp
    pages/code_ide_page.cpp
    pages/writing_page.hpp
    pages/writing_page.cpp
    pages/research_page.hpp
    pages/research_page.cpp
    pages/character_page.hpp
    pages/character_page.cpp
    pages/learn_page.hpp
    pages/learn_page.cpp
    pages/settings_page.hpp
    pages/settings_page.cpp
    builder/builder_data_models.hpp
    builder/builder_data_models.cpp
    builder/cartridge_graph_bridge.hpp
    builder/cartridge_graph_bridge.cpp
    builder/recipe_builder_page.hpp
    builder/recipe_builder_page.cpp
    dialogs/setup_wizard.hpp
    dialogs/setup_wizard.cpp
    dialogs/plan_review_dialog.hpp
    dialogs/plan_review_dialog.cpp
)
target_include_directories(aquila_gui PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(aquila_gui PRIVATE aquila::core aquila_llamacpp Qt6::Widgets Qt6::OpenGL QtNodes::QtNodes)
aquila_set_warnings(aquila_gui)

get_target_property(_qmake Qt6::qmake IMPORTED_LOCATION)
get_filename_component(AQUILA_QT_BIN_DIR "${_qmake}" DIRECTORY)

add_test(NAME gui.smoke COMMAND aquila_gui --smoke)
set_tests_properties(gui.smoke PROPERTIES
    PASS_REGULAR_EXPRESSION "smoke=ok")
if(NOT WIN32)
    set_property(TEST gui.smoke PROPERTY ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()
aquila_test_env(gui.smoke "${AQUILA_QT_BIN_DIR}")

add_test(NAME gui.headless COMMAND aquila_gui --test-headless)
set_tests_properties(gui.headless PROPERTIES
    PASS_REGULAR_EXPRESSION "\\[GUI-HEADLESS-TEST-OK\\]")
if(NOT WIN32)
    set_property(TEST gui.headless PROPERTY ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()
aquila_test_env(gui.headless "${AQUILA_QT_BIN_DIR}")
