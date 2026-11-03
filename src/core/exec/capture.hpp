#pragma once

#include <algorithm>
#include <cstddef>
#include <string>

namespace aquila::exec::detail {

// Keeps the first and last max/2 bytes of a stream (compiler errors come first,
// summaries last) and counts the rest.
class Capture {
public:
    explicit Capture(std::size_t max_bytes) : half_(max_bytes / 2) {}

    void add(const char* data, std::size_t n) {
        total_ += n;
        std::size_t i = 0;
        if (head_.size() < half_) {
            const auto take = std::min(n, half_ - head_.size());
            head_.append(data, take);
            i = take;
        }
        if (i < n) {
            tail_.append(data + i, n - i);
            if (tail_.size() > 2 * half_) tail_.erase(0, tail_.size() - half_);
        }
    }

    [[nodiscard]] std::size_t total() const noexcept { return total_; }
    [[nodiscard]] bool truncated() const noexcept { return head_.size() + std::min(tail_.size(), half_) < total_; }

    [[nodiscard]] std::string str() const {
        const std::string tail = tail_.size() > half_ ? tail_.substr(tail_.size() - half_) : tail_;
        if (!truncated()) return head_ + tail;
        const auto dropped = total_ - head_.size() - tail.size();
        return head_ + "\n...[" + std::to_string(dropped) + " bytes of output omitted]...\n" + tail;
    }

private:
    std::size_t half_;
    std::size_t total_ = 0;
    std::string head_;
    std::string tail_;
};

}  // namespace aquila::exec::detail
