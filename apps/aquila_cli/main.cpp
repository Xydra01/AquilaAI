#include "aquila/core.hpp"

#include <cstdio>
#include <string_view>

int main(int argc, char** argv) {
    if (argc == 2 && std::string_view(argv[1]) == "--version") {
        const auto v = aquila::version();
        std::printf("aquila %.*s\n", static_cast<int>(v.size()), v.data());
        return 0;
    }
    std::fprintf(stderr, "usage: aquila_cli --version\n");
    return 2;
}
