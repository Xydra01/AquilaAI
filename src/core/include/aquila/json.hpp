#pragma once

#include <nlohmann/json.hpp>

#include <cstdint>
#include <initializer_list>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace aquila {

// ordered_json keeps object keys in insertion order, so free-form blobs (args,
// initial_state, JSON schemas) re-serialize byte-identically.
using Json = nlohmann::ordered_json;

// Thrown for any malformed input. path() is a JSON Pointer ("" = document root).
class SchemaError : public std::runtime_error {
public:
    SchemaError(std::string path, const std::string& reason);
    [[nodiscard]] const std::string& path() const noexcept { return path_; }
    [[nodiscard]] const std::string& reason() const noexcept { return reason_; }

private:
    std::string path_;
    std::string reason_;
};

namespace json_io {

// Parses JSON text; syntax errors become SchemaError with path "".
Json parse_text(std::string_view text);

// Canonical form: 2-space indent, UTF-8 not escaped, trailing newline.
// Invalid UTF-8 in a string value throws SchemaError.
std::string canonical_dump(const Json& value);

std::string child_path(const std::string& path, std::string_view key);
std::string index_path(const std::string& path, std::size_t index);

void expect_object(const Json& value, const std::string& path);
void reject_unknown(const Json& object, const std::string& path,
                    std::initializer_list<std::string_view> allowed);

// Returns the member `key`; throws "missing required key" if absent.
const Json& require(const Json& object, const std::string& path, std::string_view key);

std::string read_string(const Json& value, const std::string& path);
bool read_bool(const Json& value, const std::string& path);
std::uint64_t read_u64(const Json& value, const std::string& path);
std::vector<std::string> read_string_array(const Json& value, const std::string& path);
// A free-form JSON object (contents unchecked).
Json read_object(const Json& value, const std::string& path);

template <class T, class ReadElem>
std::vector<T> read_array(const Json& value, const std::string& path, ReadElem&& read_elem) {
    if (!value.is_array()) {
        throw SchemaError(path, "expected array");
    }
    std::vector<T> out;
    out.reserve(value.size());
    for (std::size_t i = 0; i < value.size(); ++i) {
        out.push_back(read_elem(value[i], index_path(path, i)));
    }
    return out;
}

}  // namespace json_io

// Generic entry points; each type provides
//   void to_json(Json&, const T&)
//   void from_json(const Json&, T&, const std::string& path)
template <class T>
T parse(std::string_view text) {
    T value{};
    from_json(json_io::parse_text(text), value, std::string{});
    return value;
}

template <class T>
std::string to_canonical_string(const T& value) {
    Json j;
    to_json(j, value);
    return json_io::canonical_dump(j);
}

}  // namespace aquila
