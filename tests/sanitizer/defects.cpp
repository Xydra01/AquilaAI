// Deliberate defects. Each mode must be reported by the sanitizer configured for
// the build; ctest matches the report text, so an unrelated crash does not pass.
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>

#if defined(_MSC_VER) && defined(_DEBUG)
#include <crtdbg.h>
#endif

#if defined(__has_feature)
#if __has_feature(address_sanitizer)
#define AQUILA_HAS_ASAN 1
#endif
#endif
#if !defined(AQUILA_HAS_ASAN) && defined(__SANITIZE_ADDRESS__)
#define AQUILA_HAS_ASAN 1
#endif
#ifndef AQUILA_HAS_ASAN
#define AQUILA_HAS_ASAN 0
#endif

namespace {

volatile int g_index = 4;
volatile int g_int_max = INT_MAX;

int heap_overflow() {
    auto buf = std::make_unique<int[]>(4);
    buf[static_cast<std::size_t>(g_index)] = 1;
    return buf[0];
}

int use_after_free() {
    int* p = new int(7);
    delete p;
    return *static_cast<int volatile*>(p);
}

int signed_overflow() {
    int a = g_int_max;
    int b = a + 1;
    std::printf("%d\n", b);
    return 0;
}

// LSan scans stacks conservatively, and a stale copy of a dropped pointer can survive
// in dead stack memory reused by exit(). Reusing one slot for 8 blocks guarantees at
// least 7 are unreachable.
int leak() {
    for (int i = 0; i < 8; ++i) {
        void* volatile p = std::malloc(64);
        std::memset(p, i, 64);
    }
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
#if defined(_MSC_VER) && defined(_DEBUG)
    _CrtSetDbgFlag(_CRTDBG_ALLOC_MEM_DF | _CRTDBG_LEAK_CHECK_DF);
    _CrtSetReportMode(_CRT_WARN, _CRTDBG_MODE_FILE);
    _CrtSetReportFile(_CRT_WARN, _CRTDBG_FILE_STDERR);
#endif
    if (argc != 2) {
        std::fprintf(stderr, "usage: aquila_defects <mode>\n");
        return 2;
    }
    const char* mode = argv[1];
    if (std::strcmp(mode, "report") == 0) {
        std::printf("asan=%d\n", AQUILA_HAS_ASAN);
        return 0;
    }
    if (std::strcmp(mode, "none") == 0) {
        std::printf("ok\n");
        return 0;
    }
    if (std::strcmp(mode, "heap_overflow") == 0) return heap_overflow();
    if (std::strcmp(mode, "use_after_free") == 0) return use_after_free();
    if (std::strcmp(mode, "signed_overflow") == 0) return signed_overflow();
    if (std::strcmp(mode, "leak") == 0) return leak();
    std::fprintf(stderr, "unknown mode: %s\n", mode);
    return 2;
}
