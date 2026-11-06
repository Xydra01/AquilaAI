#include "aquila/knowledge/embedding.hpp"

#include <cmath>
#include <cctype>

namespace aquila::knowledge {

HashingEmbedder::HashingEmbedder(std::size_t dim) : dim_(dim > 0 ? dim : 384) {}

std::vector<std::string> HashingEmbedder::extract_tokens(std::string_view text) const {
    std::string raw;
    raw.reserve(text.size());
    for (char c : text) {
        if (c == '_' || c == '-') {
            raw.push_back(' ');
        } else {
            raw.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
        }
    }

    std::vector<std::string> words;
    std::string cur;
    for (char c : raw) {
        if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) {
            cur.push_back(c);
        } else {
            if (!cur.empty()) {
                words.push_back(cur);
                cur.clear();
            }
        }
    }
    if (!cur.empty()) {
        words.push_back(cur);
    }

    std::vector<std::string> out;
    for (const auto& w : words) {
        out.push_back(w);
        if (w.size() >= 4) {
            for (int n : {3, 4}) {
                if (w.size() >= static_cast<std::size_t>(n)) {
                    for (std::size_t i = 0; i <= w.size() - static_cast<std::size_t>(n); ++i) {
                        out.push_back("ng" + std::to_string(n) + ":" + w.substr(i, n));
                    }
                }
            }
        }
    }

    if (words.size() >= 2) {
        for (std::size_t i = 0; i < words.size() - 1; ++i) {
            out.push_back("bg:" + words[i] + "_" + words[i + 1]);
        }
    }

    return out;
}

std::vector<float> HashingEmbedder::embed(std::string_view text) const {
    const auto tokens = extract_tokens(text);
    std::vector<float> vec(dim_, 0.0f);

    for (const auto& tok : tokens) {
        uint8_t digest[8] = {0};
        blake2b_64(tok.data(), tok.size(), digest);
        uint32_t idx = static_cast<uint32_t>(digest[0]) |
                      (static_cast<uint32_t>(digest[1]) << 8) |
                      (static_cast<uint32_t>(digest[2]) << 16) |
                      (static_cast<uint32_t>(digest[3]) << 24);
        idx %= static_cast<uint32_t>(dim_);
        const float sign = (digest[4] % 2 == 0) ? 1.0f : -1.0f;
        vec[idx] += sign;
    }

    double sum_sq = 0.0;
    for (float v : vec) {
        sum_sq += static_cast<double>(v) * static_cast<double>(v);
    }
    const double norm = std::sqrt(sum_sq);
    if (norm > 0.0) {
        for (float& v : vec) {
            v = static_cast<float>(static_cast<double>(v) / norm);
        }
    }
    return vec;
}

}  // namespace aquila::knowledge

