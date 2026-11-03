#pragma once

#include "aquila/json.hpp"

#include <string>

namespace aquila {

// Validates `value` against the JSON Schema subset that module actions emit:
// type, properties, required, additionalProperties (false), enum, items,
// minimum, maximum, minItems. Throws SchemaError at the offending path.
void check_schema(const Json& schema, const Json& value, const std::string& path = "");

}  // namespace aquila
