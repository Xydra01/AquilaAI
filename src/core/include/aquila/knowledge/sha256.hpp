#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <string_view>

namespace aquila::knowledge {

class Sha256 {
public:
    Sha256();
    void update(const void* data, std::size_t len);
    void update(std::string_view text);
    std::array<uint8_t, 32> finalize();
    std::string finalize_hex();

    static std::array<uint8_t, 32> hash(std::span<const uint8_t> data);
    static std::string hash_hex(std::string_view text);

private:
    uint32_t state_[8];
    uint64_t count_{0};
    uint8_t buffer_[64];

    void transform(const uint8_t block[64]);
};

} // namespace aquila::knowledge

