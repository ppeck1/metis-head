from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


class SchemaValidationError(ValueError):
    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.detail = message
        super().__init__(f"{path}: {message}")


def validate_arguments(schema: Mapping[str, Any], value: Any) -> dict[str, Any]:
    """Validate the conservative JSON Schema subset accepted by tool specs."""
    _validate(schema, value, "$")
    if not isinstance(value, dict):
        raise SchemaValidationError("$", "tool arguments must be an object")
    return dict(value)


def _validate(schema: Mapping[str, Any], value: Any, path: str) -> None:
    if "const" in schema and value != schema["const"]:
        raise SchemaValidationError(path, "value does not match const")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(path, "value is not in enum")

    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(_matches_type(value, item) for item in expected):
            raise SchemaValidationError(path, f"expected one of {expected}")
    elif isinstance(expected, str) and not _matches_type(value, expected):
        raise SchemaValidationError(path, f"expected {expected}")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for name in required:
            if name not in value:
                raise SchemaValidationError(path, f"missing required property {name!r}")
        additional = schema.get("additionalProperties", True)
        for name, child in value.items():
            child_path = f"{path}.{name}"
            if name in properties:
                _validate(properties[name], child, child_path)
            elif additional is False:
                raise SchemaValidationError(child_path, "additional property is not allowed")
            elif isinstance(additional, Mapping):
                _validate(additional, child, child_path)
        _check_count(schema, len(value), path, "Properties")
    elif isinstance(value, list):
        _check_count(schema, len(value), path, "Items")
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, child in enumerate(value):
                _validate(items, child, f"{path}[{index}]")
    elif isinstance(value, str):
        _check_count(schema, len(value), path, "Length")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise SchemaValidationError(path, "number must be finite")
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaValidationError(path, f"must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaValidationError(path, f"must be <= {schema['maximum']}")


def _check_count(schema: Mapping[str, Any], count: int, path: str, suffix: str) -> None:
    minimum = schema.get(f"min{suffix}")
    maximum = schema.get(f"max{suffix}")
    if minimum is not None and count < minimum:
        raise SchemaValidationError(path, f"contains fewer than {minimum}")
    if maximum is not None and count > maximum:
        raise SchemaValidationError(path, f"contains more than {maximum}")


def _matches_type(value: Any, expected: str) -> bool:
    return {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda: isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": lambda: isinstance(value, bool),
        "null": lambda: value is None,
    }.get(expected, lambda: False)()
