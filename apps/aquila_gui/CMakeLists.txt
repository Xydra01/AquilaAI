find_package(Qt6 6.11 QUIET COMPONENTS Widgets)
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

qt_add_executable(aquila_gui main.cpp)
target_link_libraries(aquila_gui PRIVATE aquila::core Qt6::Widgets)
aquila_set_warnings(aquila_gui)

get_target_property(_qmake Qt6::qmake IMPORTED_LOCATION)
get_filename_component(AQUILA_QT_BIN_DIR "${_qmake}" DIRECTORY)

add_test(NAME gui.smoke COMMAND aquila_gui --smoke)
set_tests_properties(gui.smoke PROPERTIES
    PASS_REGULAR_EXPRESSION "smoke=ok"
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
aquila_test_env(gui.smoke "${AQUILA_QT_BIN_DIR}")
