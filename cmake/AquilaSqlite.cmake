# SQLite 3 amalgamation with FTS5, pinned by URL + SHA256.
# Upstream build scripts are bypassed; sqlite3.c is built directly as a static library
# with warning suppression so third-party C does not break -Werror / /WX.
include(FetchContent)

FetchContent_Declare(sqlite3_amalgamation
    URL https://www.sqlite.org/2024/sqlite-amalgamation-3470200.zip
    URL_HASH SHA256=aa73d8748095808471deaa8e6f34aa700e37f2f787f4425744f53fdd15a89c40
    SOURCE_SUBDIR aquila-no-cmake
    EXCLUDE_FROM_ALL
)

FetchContent_MakeAvailable(sqlite3_amalgamation)

set(SQLITE3_SRC "${sqlite3_amalgamation_SOURCE_DIR}/sqlite3.c")
set(SQLITE3_HDR "${sqlite3_amalgamation_SOURCE_DIR}/sqlite3.h")

add_library(aquila_sqlite3 STATIC "${SQLITE3_SRC}")
target_include_directories(aquila_sqlite3 SYSTEM PUBLIC "${sqlite3_amalgamation_SOURCE_DIR}")
set_target_properties(aquila_sqlite3 PROPERTIES
    C_STANDARD 11
    C_STANDARD_REQUIRED ON
    POSITION_INDEPENDENT_CODE ON
)

target_compile_definitions(aquila_sqlite3 PUBLIC
    SQLITE_ENABLE_FTS5=1
    SQLITE_ENABLE_RTREE=1
    SQLITE_THREADSAFE=1
    SQLITE_DQS=0
    SQLITE_DEFAULT_MEMSTATUS=0
    SQLITE_DEFAULT_WAL_SYNCHRONOUS=1
    SQLITE_OMIT_DEPRECATED=1
)

if(MSVC)
    target_compile_options(aquila_sqlite3 PRIVATE /W0)
else()
    target_compile_options(aquila_sqlite3 PRIVATE -w)
endif()

