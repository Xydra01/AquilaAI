# Puts sanitizer runtime DLLs (and optionally Qt) on PATH for a test, without
# touching the user's global PATH.
function(aquila_test_env test)
    set(dirs "")
    if(WIN32 AND AQUILA_ASAN)
        get_filename_component(compiler_dir "${CMAKE_CXX_COMPILER}" DIRECTORY)
        list(APPEND dirs "${compiler_dir}")
    endif()
    list(APPEND dirs ${ARGN})
    foreach(dir IN LISTS dirs)
        file(TO_NATIVE_PATH "${dir}" native)
        set_property(TEST ${test} APPEND PROPERTY
            ENVIRONMENT_MODIFICATION "PATH=path_list_prepend:${native}")
    endforeach()
endfunction()
