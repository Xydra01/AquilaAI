#include "cli_app.hpp"

#include <iostream>

int main(int argc, char** argv) {
    const auto opts = aquila::cli::parse_args(argc, argv);
    return aquila::cli::dispatch(opts, std::cin, std::cout, std::cerr);
}
