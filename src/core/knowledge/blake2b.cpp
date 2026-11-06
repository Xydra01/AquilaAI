#include "aquila/knowledge/embedding.hpp"

#include <cstdint>
#include <cstring>

namespace aquila::knowledge {

namespace {

const uint64_t blake2b_iv[8] = {
    0x6a09e667f3bcc908ULL, 0xbb67ae8584caa73bULL,
    0x3c6ef372fe94f82bULL, 0xa54ff53a5f1d36f1ULL,
    0x510e527fade682d1ULL, 0x9b05688c2b3e6c1fULL,
    0x1f83d9abfb41bd6bULL, 0x5be0cd19137e2179ULL
};

const uint8_t blake2b_sigma[12][16] = {
    { 0,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14, 15 },
    { 14, 10,  4,  8,  9, 15, 13,  6,  1, 12,  0,  2, 11,  7,  5,  3 },
    { 11,  8, 12,  0,  5,  2, 15, 13, 10, 14,  3,  6,  7,  1,  9,  4 },
    {  7,  9,  3,  1, 13, 12, 11, 14,  2,  6,  5, 10,  4,  0, 15,  8 },
    {  9,  0,  5,  7,  2,  4, 10, 15, 14,  1, 11, 12,  6,  8,  3, 13 },
    {  2, 12,  6, 10,  0, 11,  8,  3,  4, 13,  7,  5, 15, 14,  1,  9 },
    { 12,  5,  1, 15, 14, 13,  4, 10,  0,  7,  6,  3,  9,  2,  8, 11 },
    { 13, 11,  7, 14, 12,  1,  3,  9,  5,  0, 15,  4,  8,  6,  2, 10 },
    {  6, 15, 14,  9, 11,  3,  0,  8, 12,  2, 13,  7,  1,  4, 10,  5 },
    { 10,  2,  8,  4,  7,  6,  1,  5, 15, 11,  9, 14,  3, 12, 13,  0 },
    {  0,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14, 15 },
    { 14, 10,  4,  8,  9, 15, 13,  6,  1, 12,  0,  2, 11,  7,  5,  3 }
};

inline uint64_t rotr64(uint64_t w, unsigned c) {
    return (w >> c) | (w << (64 - c));
}

inline void b2b_g(uint64_t* v, int a, int b, int c, int d, uint64_t x, uint64_t y) {
    v[a] = v[a] + v[b] + x;
    v[d] = rotr64(v[d] ^ v[a], 32);
    v[c] = v[c] + v[d];
    v[b] = rotr64(v[b] ^ v[c], 24);
    v[a] = v[a] + v[b] + y;
    v[d] = rotr64(v[d] ^ v[a], 16);
    v[c] = v[c] + v[d];
    v[b] = rotr64(v[b] ^ v[c], 63);
}

void blake2b_compress(uint64_t h[8], const uint8_t block[128], uint64_t t0, uint64_t t1, bool last) {
    uint64_t v[16];
    uint64_t m[16];

    for (int i = 0; i < 8; ++i) v[i] = h[i];
    v[8] = blake2b_iv[0];
    v[9] = blake2b_iv[1];
    v[10] = blake2b_iv[2];
    v[11] = blake2b_iv[3];
    v[12] = blake2b_iv[4] ^ t0;
    v[13] = blake2b_iv[5] ^ t1;
    v[14] = blake2b_iv[6] ^ (last ? ~0ULL : 0ULL);
    v[15] = blake2b_iv[7];

    for (int i = 0; i < 16; ++i) {
        m[i] = (static_cast<uint64_t>(block[i * 8 + 0])) |
               (static_cast<uint64_t>(block[i * 8 + 1]) << 8) |
               (static_cast<uint64_t>(block[i * 8 + 2]) << 16) |
               (static_cast<uint64_t>(block[i * 8 + 3]) << 24) |
               (static_cast<uint64_t>(block[i * 8 + 4]) << 32) |
               (static_cast<uint64_t>(block[i * 8 + 5]) << 40) |
               (static_cast<uint64_t>(block[i * 8 + 6]) << 48) |
               (static_cast<uint64_t>(block[i * 8 + 7]) << 56);
    }

    for (int r = 0; r < 12; ++r) {
        b2b_g(v, 0, 4,  8, 12, m[blake2b_sigma[r][ 0]], m[blake2b_sigma[r][ 1]]);
        b2b_g(v, 1, 5,  9, 13, m[blake2b_sigma[r][ 2]], m[blake2b_sigma[r][ 3]]);
        b2b_g(v, 2, 6, 10, 14, m[blake2b_sigma[r][ 4]], m[blake2b_sigma[r][ 5]]);
        b2b_g(v, 3, 7, 11, 15, m[blake2b_sigma[r][ 6]], m[blake2b_sigma[r][ 7]]);
        b2b_g(v, 0, 5, 10, 15, m[blake2b_sigma[r][ 8]], m[blake2b_sigma[r][ 9]]);
        b2b_g(v, 1, 6, 11, 12, m[blake2b_sigma[r][10]], m[blake2b_sigma[r][11]]);
        b2b_g(v, 2, 7,  8, 13, m[blake2b_sigma[r][12]], m[blake2b_sigma[r][13]]);
        b2b_g(v, 3, 4,  9, 14, m[blake2b_sigma[r][14]], m[blake2b_sigma[r][15]]);
    }

    for (int i = 0; i < 8; ++i) {
        h[i] = h[i] ^ v[i] ^ v[i + 8];
    }
}

}  // namespace

void blake2b_64(const void* in, std::size_t inlen, uint8_t out[8]) {
    uint64_t h[8];
    for (int i = 0; i < 8; ++i) h[i] = blake2b_iv[i];
    h[0] ^= 0x01010008ULL; // fanout=1, depth=1, digest_length=8

    const auto* p = static_cast<const uint8_t*>(in);
    std::size_t left = inlen;
    uint8_t block[128] = {0};
    uint64_t t = 0;

    while (left > 128) {
        t += 128;
        blake2b_compress(h, p, t, 0, false);
        p += 128;
        left -= 128;
    }

    t += left;
    std::memset(block, 0, sizeof(block));
    if (left > 0) {
        std::memcpy(block, p, left);
    }
    blake2b_compress(h, block, t, 0, true);

    for (int i = 0; i < 8; ++i) {
        out[i] = static_cast<uint8_t>((h[0] >> (i * 8)) & 0xff);
    }
}

}  // namespace aquila::knowledge

