#pragma once

#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <string>
#include <system_error>

namespace aquila::test {

// A fresh directory under the system temp dir, removed on destruction.
class TempDir {
public:
    TempDir() {
        static std::atomic<unsigned> counter{0};
        const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
        path_ = std::filesystem::temp_directory_path() /
                ("aquila-test-" + std::to_string(stamp) + "-" + std::to_string(counter++));
        std::filesystem::create_directories(path_);
    }
    ~TempDir() {
        std::error_code ec;
        std::filesystem::remove_all(path_, ec);
    }
    TempDir(const TempDir&) = delete;
    TempDir& operator=(const TempDir&) = delete;

    [[nodiscard]] const std::filesystem::path& path() const noexcept { return path_; }

    // Writes `bytes` exactly (binary) to a path relative to the temp dir.
    void write(const std::string& rel, const std::string& bytes) const {
        const auto p = path_ / std::filesystem::path(std::u8string(rel.begin(), rel.end()));
        std::filesystem::create_directories(p.parent_path());
        std::ofstream(p, std::ios::binary) << bytes;
    }

private:
    std::filesystem::path path_;
};

}  // namespace aquila::test
