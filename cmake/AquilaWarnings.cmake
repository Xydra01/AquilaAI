# Strict warnings for Aquila's own targets only; dependencies are fetched as SYSTEM.
function(aquila_set_warnings target)
    if(MSVC)
        # C4702 (unreachable code) is emitted by the code generator, so /external:W0
        # cannot hide it when it originates in a dependency's templates (inja parser.hpp).
        target_compile_options(${target} PRIVATE
            $<$<COMPILE_LANGUAGE:CXX>:/W4 /WX /permissive- /utf-8 /Zc:__cplusplus /wd4702 /EHsc>)
        # C4996 flags standard functions such as std::getenv as "unsafe".
        target_compile_definitions(${target} PRIVATE _CRT_SECURE_NO_WARNINGS)
    else()
        target_compile_options(${target} PRIVATE
            $<$<COMPILE_LANGUAGE:CXX>:-Wall -Wextra -Wpedantic -Werror>)
    endif()
endfunction()
