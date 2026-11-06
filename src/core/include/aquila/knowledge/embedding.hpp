#pragma once

#include <cstddef>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace aquila::knowledge {

class IEmbeddingEngine {
public:
    virtual ~IEmbeddingEngine() = default;
    virtual std::vector<float> embed(std::string_view text) const = 0;
    virtual std::size_t dimension() const noexcept = 0;
};

// RFC 7693 Blake2b-64 standalone hash function
void blake2b_64(const void* in, std::size_t inlen, uint8_t out[8]);

class HashingEmbedder final : public IEmbeddingEngine {
public:
    explicit HashingEmbedder(std::size_t dim = 384);
    ~HashingEmbedder() override = default;

    std::vector<float> embed(std::string_view text) const override;
    std::size_t dimension() const noexcept override { return dim_; }

    // Feature extraction helpers
    std::vector<std::string> extract_tokens(std::string_view text) const;

private:
    std::size_t dim_{384};
};

}  // namespace aquila::knowledge

