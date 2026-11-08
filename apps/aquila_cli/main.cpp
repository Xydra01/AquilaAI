#include "cli_app.hpp"

#include <exception>
#include <iostream>

int main(int argc, char** argv) {
    std::set_terminate([]() {
        try {
            auto ex = std::current_exception();
            if (ex) {
                std::rethrow_exception(ex);
            }
        } catch (const std::exception& e) {
            std::cerr << "\n[FATAL TERMINATE EXCEPTION]: " << e.what() << "\n";
        } catch (...) {
            std::cerr << "\n[FATAL TERMINATE UNKNOWN EXCEPTION]\n";
        }
        std::abort();
    });

    try {
        const auto opts = aquila::cli::parse_args(argc, argv);
        return aquila::cli::dispatch(opts, std::cin, std::cout, std::cerr);
    } catch (const std::exception& e) {
        std::cerr << "\n[MAIN UNHANDLED EXCEPTION]: " << e.what() << "\n";
        return 1;
    } catch (...) {
        std::cerr << "\n[MAIN UNHANDLED UNKNOWN EXCEPTION]\n";
        return 1;
    }
}
