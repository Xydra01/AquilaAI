#include "aquila/knowledge/sha256.hpp"

#include <algorithm>
#include <cstring>
#include <iomanip>
#include <sstream>

namespace aquila::knowledge {

namespace {

constexpr uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

inline uint32_t ror(uint32_t x, uint32_t n) noexcept {
    return (x >> n) | (x << (32 - n));
}

inline uint32_t ch(uint32_t x, uint32_t y, uint32_t z) noexcept {
    return (x & y) ^ (~x & z);
}

inline uint32_t maj(uint32_t x, uint32_t y, uint32_t z) noexcept {
    return (x & y) ^ (x & z) ^ (y & z);
}

inline uint32_t ep0(uint32_t x) noexcept {
    return ror(x, 2) ^ ror(x, 13) ^ ror(x, 22);
}

inline uint32_t ep1(uint32_t x) noexcept {
    return ror(x, 6) ^ ror(x, 11) ^ ror(x, 25);
}

inline uint32_t sig0(uint32_t x) noexcept {
    return ror(x, 7) ^ ror(x, 18) ^ (x >> 3);
}

inline uint32_t sig1(uint32_t x) noexcept {
    return ror(x, 17) ^ ror(x, 19) ^ (x >> 10);
}

} // namespace

Sha256::Sha256() {
    state_[0] = 0x6a09e667;
    state_[1] = 0xbb67ae85;
    state_[2] = 0x3c6ef372;
    state_[3] = 0xa54ff53a;
    state_[4] = 0x510e527f;
    state_[5] = 0x9b05688c;
    state_[6] = 0x1f83d9ab;
    state_[7] = 0x5be0cd19;
    count_ = 0;
    std::memset(buffer_, 0, sizeof(buffer_));
}

void Sha256::transform(const uint8_t block[64]) {
    uint32_t w[64];
    for (int i = 0; i < 16; ++i) {
        w[i] = (static_cast<uint32_t>(block[i * 4]) << 24) |
               (static_cast<uint32_t>(block[i * 4 + 1]) << 16) |
               (static_cast<uint32_t>(block[i * 4 + 2]) << 8) |
               (static_cast<uint32_t>(block[i * 4 + 3]));
    }
    for (int i = 16; i < 64; ++i) {
        w[i] = sig1(w[i - 2]) + w[i - 7] + sig0(w[i - 15]) + w[i - 16];
    }

    uint32_t a = state_[0];
    uint32_t b = state_[1];
    uint32_t c = state_[2];
    uint32_t d = state_[3];
    uint32_t e = state_[4];
    uint32_t f = state_[5];
    uint32_t g = state_[6];
    uint32_t h = state_[7];

    for (int i = 0; i < 64; ++i) {
        uint32_t t1 = h + ep1(e) + ch(e, f, g) + K[i] + w[i];
        uint32_t t2 = ep0(a) + maj(a, b, c);
        h = g;
        g = f;
        f = e;
        e = d + t1;
        d = c;
        c = b;
        b = a;
        a = t1 + t2;
    }

    state_[0] += a;
    state_[1] += b;
    state_[2] += c;
    state_[3] += d;
    state_[4] += e;
    state_[5] += f;
    state_[6] += g;
    state_[7] += h;
}

void Sha256::update(const void* data, std::size_t len) {
    const auto* bytes = static_cast<const uint8_t*>(data);
    std::size_t buffer_idx = static_cast<std::size_t>(count_ % 64);
    count_ += len;

    std::size_t space = 64 - buffer_idx;
    if (len >= space) {
        std::memcpy(buffer_ + buffer_idx, bytes, space);
        transform(buffer_);
        bytes += space;
        len -= space;
        while (len >= 64) {
            transform(bytes);
            bytes += 64;
            len -= 64;
        }
        buffer_idx = 0;
    }
    if (len > 0) {
        std::memcpy(buffer_ + buffer_idx, bytes, len);
    }
}

void Sha256::update(std::string_view text) {
    update(text.data(), text.size());
}

std::array<uint8_t, 32> Sha256::finalize() {
    const uint64_t total_bits = count_ * 8;

    uint8_t pad[64] = {0};
    pad[0] = 0x80;

    const std::size_t rem = static_cast<std::size_t>(count_ % 64);
    const std::size_t pad_len = (rem < 56) ? (56 - rem) : (120 - rem);

    update(pad, 1);
    if (pad_len > 1) {
        std::size_t zeros = pad_len - 1;
        while (zeros > 0) {
            std::size_t chunk = std::min(zeros, sizeof(pad));
            update(pad + 1, chunk);
            zeros -= chunk;
        }
    }

    uint8_t len_bytes[8];
    for (int i = 0; i < 8; ++i) {
        len_bytes[7 - i] = static_cast<uint8_t>((total_bits >> (i * 8)) & 0xFF);
    }
    update(len_bytes, 8);

    std::array<uint8_t, 32> digest{};
    for (int i = 0; i < 8; ++i) {
        digest[i * 4] = static_cast<uint8_t>((state_[i] >> 24) & 0xFF);
        digest[i * 4 + 1] = static_cast<uint8_t>((state_[i] >> 16) & 0xFF);
        digest[i * 4 + 2] = static_cast<uint8_t>((state_[i] >> 8) & 0xFF);
        digest[i * 4 + 3] = static_cast<uint8_t>(state_[i] & 0xFF);
    }
    return digest;
}

std::string Sha256::finalize_hex() {
    auto digest = finalize();
    static constexpr char hex_chars[] = "0123456789abcdef";
    std::string hex;
    hex.reserve(64);
    for (uint8_t b : digest) {
        hex.push_back(hex_chars[(b >> 4) & 0x0F]);
        hex.push_back(hex_chars[b & 0x0F]);
    }
    return hex;
}

std::array<uint8_t, 32> Sha256::hash(std::span<const uint8_t> data) {
    Sha256 s;
    s.update(data.data(), data.size());
    return s.finalize();
}

std::string Sha256::hash_hex(std::string_view text) {
    Sha256 s;
    s.update(text);
    return s.finalize_hex();
}

} // namespace aquila::knowledge
