#include "aquila/json.hpp"

#include <algorithm>
#include <set>
#include <utility>

namespace aquila {

SchemaError::SchemaError(std::string path, const std::string& reason)
    : std::runtime_error((path.empty() ? std::string("(root)") : path) + ": " + reason),
      path_(std::move(path)),
      reason_(reason) {}

namespace json_io {

namespace {

const char* type_name(const Json& v) {
    return v.type_name();
}

}  // namespace

Json parse_text(std::string_view text) {
    // nlohmann accepts duplicate object keys silently; a strict schema must not.
    std::vector<std::set<std::string>> open_objects;
    const Json::parser_callback_t reject_duplicates =
        [&open_objects](int, Json::parse_event_t event, Json& parsed) {
            switch (event) {
                case Json::parse_event_t::object_start:
                    open_objects.emplace_back();
                    break;
                case Json::parse_event_t::object_end:
                    open_objects.pop_back();
                    break;
                case Json::parse_event_t::key: {
                    auto key = parsed.get<std::string>();
                    if (!open_objects.back().insert(key).second) {
                        throw SchemaError("", "invalid JSON: duplicate key '" + key + "'");
                    }
                    break;
                }
                default:
                    break;
            }
            return true;
        };
    try {
        return Json::parse(text.begin(), text.end(), reject_duplicates);
    } catch (const Json::parse_error& e) {
        throw SchemaError("", std::string("invalid JSON: ") + e.what());
    }
}

std::string canonical_dump(const Json& value) {
    try {
        return value.dump(2, ' ', false, Json::error_handler_t::strict) + "\n";
    } catch (const Json::type_error& e) {
        throw SchemaError("", std::string("cannot serialize: ") + e.what());
    }
}

std::string sanitize_utf8(std::string_view s) {
    std::string out;
    out.reserve(s.size());
    const auto* p = reinterpret_cast<const unsigned char*>(s.data());
    const std::size_t len = s.size();
    std::size_t i = 0;

    constexpr std::string_view kReplacement = "\xEF\xBF\xBD"; // U+FFFD

    while (i < len) {
        const unsigned char b0 = p[i];
        if (b0 < 0x80) {
            out.push_back(static_cast<char>(b0));
            ++i;
        } else if (b0 >= 0xC2 && b0 <= 0xDF) {
            if (i + 1 < len && (p[i + 1] & 0xC0) == 0x80) {
                out.append(reinterpret_cast<const char*>(&p[i]), 2);
                i += 2;
            } else {
                out.append(kReplacement);
                ++i;
            }
        } else if (b0 == 0xE0) {
            if (i + 2 < len && (p[i + 1] >= 0xA0 && p[i + 1] <= 0xBF) && (p[i + 2] & 0xC0) == 0x80) {
                out.append(reinterpret_cast<const char*>(&p[i]), 3);
                i += 3;
            } else {
                out.append(kReplacement);
                ++i;
            }
        } else if ((b0 >= 0xE1 && b0 <= 0xEC) || b0 == 0xEE || b0 == 0xEF) {
            if (i + 2 < len && (p[i + 1] & 0xC0) == 0x80 && (p[i + 2] & 0xC0) == 0x80) {
                out.append(reinterpret_cast<const char*>(&p[i]), 3);
                i += 3;
            } else {
                out.append(kReplacement);
                ++i;
            }
        } else if (b0 == 0xED) {
            if (i + 2 < len && (p[i + 1] >= 0x80 && p[i + 1] <= 0x9F) && (p[i + 2] & 0xC0) == 0x80) {
                out.append(reinterpret_cast<const char*>(&p[i]), 3);
                i += 3;
            } else {
                out.append(kReplacement);
                ++i;
            }
        } else if (b0 == 0xF0) {
            if (i + 3 < len && (p[i + 1] >= 0x90 && p[i + 1] <= 0xBF) && (p[i + 2] & 0xC0) == 0x80 && (p[i + 3] & 0xC0) == 0x80) {
                out.append(reinterpret_cast<const char*>(&p[i]), 4);
                i += 4;
            } else {
                out.append(kReplacement);
                ++i;
            }
        } else if (b0 >= 0xF1 && b0 <= 0xF3) {
            if (i + 3 < len && (p[i + 1] & 0xC0) == 0x80 && (p[i + 2] & 0xC0) == 0x80 && (p[i + 3] & 0xC0) == 0x80) {
                out.append(reinterpret_cast<const char*>(&p[i]), 4);
                i += 4;
            } else {
                out.append(kReplacement);
                ++i;
            }
        } else if (b0 == 0xF4) {
            if (i + 3 < len && (p[i + 1] >= 0x80 && p[i + 1] <= 0x8F) && (p[i + 2] & 0xC0) == 0x80 && (p[i + 3] & 0xC0) == 0x80) {
                out.append(reinterpret_cast<const char*>(&p[i]), 4);
                i += 4;
            } else {
                out.append(kReplacement);
                ++i;
            }
        } else {
            out.append(kReplacement);
            ++i;
        }
    }
    return out;
}

std::string truncate_utf8(std::string_view s, std::size_t max_bytes, std::string_view suffix) {
    if (s.size() <= max_bytes) {
        return sanitize_utf8(s);
    }
    std::size_t cut = max_bytes;
    while (cut > 0 && (static_cast<unsigned char>(s[cut]) & 0xC0) == 0x80) {
        --cut;
    }
    std::string result = sanitize_utf8(s.substr(0, cut));
    result.append(suffix);
    return result;
}

std::string child_path(const std::string& path, std::string_view key) {
    std::string out = path;
    out += '/';
    for (const char c : key) {
        if (c == '~') {
            out += "~0";
        } else if (c == '/') {
            out += "~1";
        } else {
            out += c;
        }
    }
    return out;
}

std::string index_path(const std::string& path, std::size_t index) {
    return path + "/" + std::to_string(index);
}

void expect_object(const Json& value, const std::string& path) {
    if (!value.is_object()) {
        throw SchemaError(path, std::string("expected object, got ") + type_name(value));
    }
}

void reject_unknown(const Json& object, const std::string& path,
                    std::initializer_list<std::string_view> allowed) {
    for (const auto& [key, _] : object.items()) {
        if (std::find(allowed.begin(), allowed.end(), key) == allowed.end()) {
            throw SchemaError(child_path(path, key), "unknown key");
        }
    }
}

const Json& require(const Json& object, const std::string& path, std::string_view key) {
    const auto it = object.find(std::string(key));
    if (it == object.end()) {
        throw SchemaError(child_path(path, key), "missing required key");
    }
    return *it;
}

std::string read_string(const Json& value, const std::string& path) {
    if (!value.is_string()) {
        throw SchemaError(path, std::string("expected string, got ") + type_name(value));
    }
    return value.get<std::string>();
}

bool read_bool(const Json& value, const std::string& path) {
    if (!value.is_boolean()) {
        throw SchemaError(path, std::string("expected boolean, got ") + type_name(value));
    }
    return value.get<bool>();
}

std::uint64_t read_u64(const Json& value, const std::string& path) {
    if (value.is_number_unsigned()) {
        return value.get<std::uint64_t>();
    }
    if (value.is_number_integer()) {
        const auto signed_value = value.get<std::int64_t>();
        if (signed_value >= 0) {
            return static_cast<std::uint64_t>(signed_value);
        }
        throw SchemaError(path, "expected non-negative integer, got negative");
    }
    throw SchemaError(path, std::string("expected non-negative integer, got ") + type_name(value));
}

std::vector<std::string> read_string_array(const Json& value, const std::string& path) {
    return read_array<std::string>(value, path, read_string);
}

Json read_object(const Json& value, const std::string& path) {
    expect_object(value, path);
    return value;
}

std::string opt_string(const Json& object, std::string_view key, std::string_view fallback) {
    if (!object.is_object()) return std::string(fallback);
    const auto it = object.find(std::string(key));
    if (it != object.end() && it->is_string()) {
        return it->get<std::string>();
    }
    return std::string(fallback);
}

bool opt_bool(const Json& object, std::string_view key, bool fallback) {
    if (!object.is_object()) return fallback;
    const auto it = object.find(std::string(key));
    if (it != object.end() && it->is_boolean()) {
        return it->get<bool>();
    }
    return fallback;
}

int opt_int(const Json& object, std::string_view key, int fallback) {
    if (!object.is_object()) return fallback;
    const auto it = object.find(std::string(key));
    if (it != object.end() && it->is_number_integer()) {
        return it->get<int>();
    }
    return fallback;
}

}  // namespace json_io
}  // namespace aquila
