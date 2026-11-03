# Applies AQUILA_SANITIZE globally (our targets and fetched dependencies).
#   MSVC:  address only (no UBSan/LSan in MSVC). Leak checks use the CRT debug heap.
#   Clang: address, undefined, leak (leak is Linux-only; llvm-mingw ships no LSan).

set(AQUILA_ASAN OFF)
set(AQUILA_UBSAN OFF)
set(AQUILA_LSAN OFF)

if(NOT AQUILA_SANITIZE)
    return()
endif()

foreach(san IN LISTS AQUILA_SANITIZE)
    if(san STREQUAL "address")
        set(AQUILA_ASAN ON)
    elseif(san STREQUAL "undefined")
        set(AQUILA_UBSAN ON)
    elseif(san STREQUAL "leak")
        set(AQUILA_LSAN ON)
    else()
        message(FATAL_ERROR "AQUILA_SANITIZE: unknown sanitizer '${san}'")
    endif()
endforeach()

if(MSVC)
    if(AQUILA_UBSAN OR AQUILA_LSAN)
        message(FATAL_ERROR "MSVC supports only AQUILA_SANITIZE=address")
    endif()
    add_compile_options($<$<COMPILE_LANGUAGE:C,CXX>:/fsanitize=address>)
    # ASan is incompatible with /RTC and incremental linking.
    foreach(var CMAKE_CXX_FLAGS_DEBUG CMAKE_C_FLAGS_DEBUG)
        string(REGEX REPLACE "/RTC[1csu]+" "" ${var} "${${var}}")
    endforeach()
    foreach(var CMAKE_EXE_LINKER_FLAGS_DEBUG CMAKE_SHARED_LINKER_FLAGS_DEBUG)
        string(REGEX REPLACE "/INCREMENTAL(:YES)?" "" ${var} "${${var}}")
        string(APPEND ${var} " /INCREMENTAL:NO")
    endforeach()
else()
    if(AQUILA_LSAN AND WIN32)
        message(FATAL_ERROR "LeakSanitizer is not available on Windows targets")
    endif()
    set(_flags "")
    if(AQUILA_ASAN)
        list(APPEND _flags address)
    endif()
    if(AQUILA_UBSAN)
        list(APPEND _flags undefined)
    endif()
    # On Linux, LSan is part of ASan; standalone LSan only when ASan is off.
    if(AQUILA_LSAN AND NOT AQUILA_ASAN)
        list(APPEND _flags leak)
    endif()
    list(JOIN _flags "," _joined)
    add_compile_options(
        $<$<COMPILE_LANGUAGE:C,CXX>:-fsanitize=${_joined}>
        $<$<COMPILE_LANGUAGE:C,CXX>:-fno-sanitize-recover=all>
        $<$<COMPILE_LANGUAGE:C,CXX>:-fno-omit-frame-pointer>)
    add_link_options(-fsanitize=${_joined})
endif()

message(STATUS "Aquila sanitizers: asan=${AQUILA_ASAN} ubsan=${AQUILA_UBSAN} lsan=${AQUILA_LSAN}")
