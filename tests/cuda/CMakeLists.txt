add_executable(aquila_cuda_smoke vector_add.cu)
set_target_properties(aquila_cuda_smoke PROPERTIES CUDA_STANDARD 20 CUDA_STANDARD_REQUIRED ON)

add_test(NAME cuda.vector_add COMMAND aquila_cuda_smoke)
set_tests_properties(cuda.vector_add PROPERTIES
    PASS_REGULAR_EXPRESSION "vector_add: 1048576/1048576 correct"
    LABELS cuda)

# Negative control: a wrong expected value must be detected as a mismatch.
add_test(NAME cuda.vector_add_negative COMMAND aquila_cuda_smoke --expect-wrong)
set_tests_properties(cuda.vector_add_negative PROPERTIES
    PASS_REGULAR_EXPRESSION "mismatch at index 0"
    LABELS cuda)
