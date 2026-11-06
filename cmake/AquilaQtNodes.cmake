# cmake/AquilaQtNodes.cmake
# QtNodes node editor library, pinned by URL + SHA256.
include(FetchContent)

set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_DOCS OFF CACHE BOOL "" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(USE_QT6 ON CACHE BOOL "" FORCE)
set(QT_NODES_DEVELOPER_DEFAULTS OFF CACHE BOOL "" FORCE)

FetchContent_Declare(QtNodes
    URL https://github.com/paceholder/nodeeditor/archive/refs/tags/3.0.16.tar.gz
    URL_HASH SHA256=453e6eb783379fee6edf9282283576eaa7d27349b8731e638926ccbd8331f7ef
    SYSTEM EXCLUDE_FROM_ALL
)

FetchContent_MakeAvailable(QtNodes)

if(TARGET QtNodes)
    # Silence warnings in third-party QtNodes source under strict compiler flags
    if(MSVC)
        target_compile_options(QtNodes PRIVATE /W0)
    else()
        target_compile_options(QtNodes PRIVATE -w)
    endif()
endif()

