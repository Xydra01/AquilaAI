# RapidCheck: property-based testing for the unit suite, pinned by URL + SHA256.
# RapidCheck has no versioned releases, so a specific commit archive is pinned
# (the version/commit is recorded in docs/recon/RECON_MAP.md section 1).
#
# RapidCheck is not header-only: it compiles a small static `rapidcheck` library
# and ships a Catch2 integration header at extras/catch/include/rapidcheck/catch.h.
#
# We deliberately leave RapidCheck's own RC_ENABLE_CATCH OFF: upstream keys that
# option on its ext/catch git submodule (a bundled Catch2 used only for its own
# tests), which is absent from the source archive, so enabling it breaks
# configure. We already provide Catch2 3.x (AquilaDeps.cmake), so instead of
# RapidCheck's rapidcheck_catch target we build the `rapidcheck` library and
# expose the Catch2 integration header ourselves through an INTERFACE target.
include(FetchContent)

# Only the rapidcheck library is wanted; keep its tests/examples/integrations off.
set(RC_ENABLE_TESTS OFF CACHE BOOL "" FORCE)
set(RC_ENABLE_EXAMPLES OFF CACHE BOOL "" FORCE)
set(RC_ENABLE_CATCH OFF CACHE BOOL "" FORCE)
set(RC_ENABLE_DOCTEST OFF CACHE BOOL "" FORCE)
set(RC_ENABLE_GMOCK OFF CACHE BOOL "" FORCE)
set(RC_ENABLE_GTEST OFF CACHE BOOL "" FORCE)
set(RC_ENABLE_BOOST OFF CACHE BOOL "" FORCE)
set(RC_ENABLE_BOOST_TEST OFF CACHE BOOL "" FORCE)
set(RC_INSTALL_ALL_EXTRAS OFF CACHE BOOL "" FORCE)

FetchContent_Declare(rapidcheck
    URL https://github.com/emil-e/rapidcheck/archive/2c3c4365aca21ef4e612768fdc95b1ce8b39a651.tar.gz
    URL_HASH SHA256=d7c87d2a728b9cd7adec09aed44f34938cd1b0928b373f9b490c5b2f6d5ab9dc
    SYSTEM EXCLUDE_FROM_ALL)

FetchContent_MakeAvailable(rapidcheck)

if(TARGET rapidcheck AND MSVC)
    target_compile_options(rapidcheck PRIVATE /EHsc)
endif()

# Catch2 integration target, assembled here instead of via RapidCheck's own
# rapidcheck_catch (see note above). The include is SYSTEM so RapidCheck's
# templates never trip our /W4 /WX or -Wall -Wextra -Wpedantic -Werror lanes
# (RapidCheck is known not to be clean under -Werror); the suppression is scoped
# to this dependency only, the same way tree-sitter's warnings are scoped in
# cmake/AquilaTreeSitter.cmake. rapidcheck/catch.h includes a Catch2 header only
# when none has been seen yet, so it composes with Catch2 3.x already linked.
if(NOT TARGET rapidcheck_catch)
    add_library(rapidcheck_catch INTERFACE)
    target_link_libraries(rapidcheck_catch INTERFACE rapidcheck)
    target_include_directories(rapidcheck_catch SYSTEM INTERFACE
        "${rapidcheck_SOURCE_DIR}/extras/catch/include")
endif()
