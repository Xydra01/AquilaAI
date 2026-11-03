#include <cuda_runtime.h>

#include <cstdio>
#include <cstring>
#include <vector>

namespace {

__global__ void add(const float* a, const float* b, float* c, int n) {
    const int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) c[i] = a[i] + b[i];
}

bool ok(cudaError_t err, const char* what) {
    if (err != cudaSuccess) {
        std::fprintf(stderr, "%s failed: %s\n", what, cudaGetErrorString(err));
        return false;
    }
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    const bool expect_wrong = argc == 2 && std::strcmp(argv[1], "--expect-wrong") == 0;
    constexpr int n = 1 << 20;
    std::vector<float> a(n), b(n), c(n);
    for (int i = 0; i < n; ++i) {
        a[i] = static_cast<float>(i);
        b[i] = static_cast<float>(2 * i);
    }

    cudaDeviceProp prop{};
    if (!ok(cudaGetDeviceProperties(&prop, 0), "cudaGetDeviceProperties")) return 1;
    std::printf("device=%s sm_%d%d\n", prop.name, prop.major, prop.minor);

    float *da = nullptr, *db = nullptr, *dc = nullptr;
    const size_t bytes = n * sizeof(float);
    if (!ok(cudaMalloc(&da, bytes), "cudaMalloc a") || !ok(cudaMalloc(&db, bytes), "cudaMalloc b") ||
        !ok(cudaMalloc(&dc, bytes), "cudaMalloc c"))
        return 1;
    ok(cudaMemcpy(da, a.data(), bytes, cudaMemcpyHostToDevice), "copy a");
    ok(cudaMemcpy(db, b.data(), bytes, cudaMemcpyHostToDevice), "copy b");
    add<<<(n + 255) / 256, 256>>>(da, db, dc, n);
    if (!ok(cudaGetLastError(), "kernel launch") || !ok(cudaDeviceSynchronize(), "kernel")) return 1;
    ok(cudaMemcpy(c.data(), dc, bytes, cudaMemcpyDeviceToHost), "copy c");
    cudaFree(da);
    cudaFree(db);
    cudaFree(dc);

    int correct = 0;
    for (int i = 0; i < n; ++i) {
        const float expected = static_cast<float>(3 * i) + (expect_wrong ? 1.0f : 0.0f);
        if (c[i] == expected) {
            ++correct;
        } else if (correct == i) {
            std::printf("mismatch at index %d: got %.1f expected %.1f\n", i, c[i], expected);
        }
    }
    std::printf("vector_add: %d/%d correct\n", correct, n);
    return correct == n ? 0 : 1;
}
