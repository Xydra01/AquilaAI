#include "aquila/modules/schema_check.hpp"

#include <algorithm>

namespace aquila {

namespace {

bool has_type(const Json& v, const std::string& type) {
    if (type == "string") return v.is_string();
    if (type == "integer") return v.is_number_integer();
    if (type == "number") return v.is_number();
    if (type == "boolean") return v.is_boolean();
    if (type == "object") return v.is_object();
    if (type == "array") return v.is_array();
    if (type == "null") return v.is_null();
    return false;
}

}  // namespace

void check_schema(const Json& schema, const Json& value, const std::string& path) {
    if (const auto t = schema.find("type"); t != schema.end()) {
        const auto type = t->get<std::string>();
        if (!has_type(value, type)) {
            throw SchemaError(path, "expected " + type + ", got " + value.type_name());
        }
    }
    if (const auto e = schema.find("enum"); e != schema.end()) {
        if (std::find(e->begin(), e->end(), value) == e->end()) {
            throw SchemaError(path, "value " + value.dump() + " is not one of " + e->dump());
        }
    }
    if (value.is_number()) {
        if (const auto m = schema.find("minimum"); m != schema.end() && value.get<double>() < m->get<double>()) {
            throw SchemaError(path, "must be >= " + m->dump());
        }
        if (const auto m = schema.find("maximum"); m != schema.end() && value.get<double>() > m->get<double>()) {
            throw SchemaError(path, "must be <= " + m->dump());
        }
    }
    if (value.is_object()) {
        const auto props = schema.find("properties");
        if (const auto req = schema.find("required"); req != schema.end()) {
            for (const auto& name : *req) {
                if (!value.contains(name.get<std::string>())) {
                    throw SchemaError(json_io::child_path(path, name.get<std::string>()), "missing required key");
                }
            }
        }
        const auto extra = schema.find("additionalProperties");
        const bool closed = extra != schema.end() && extra->is_boolean() && !extra->get<bool>();
        for (const auto& [key, v] : value.items()) {
            const bool known = props != schema.end() && props->contains(key);
            if (known) {
                check_schema((*props)[key], v, json_io::child_path(path, key));
            } else if (closed) {
                throw SchemaError(json_io::child_path(path, key), "unknown key");
            }
        }
    }
    if (value.is_array()) {
        if (const auto m = schema.find("minItems"); m != schema.end() && value.size() < m->get<std::size_t>()) {
            throw SchemaError(path, "must have at least " + m->dump() + " items");
        }
        if (const auto items = schema.find("items"); items != schema.end()) {
            for (std::size_t i = 0; i < value.size(); ++i) {
                check_schema(*items, value[i], json_io::index_path(path, i));
            }
        }
    }
}

}  // namespace aquila
