from typing import Dict, Any, List
from .parser import ParseError


def validate_fields(fields: List[Dict[str, Any]]) -> None:
    """
    Cross-validate field definitions.
    Ensures constraints are compatible with the declared type.
    """
    for field in fields:
        name  = field["name"]
        ftype = field["type"]

        # numeric-only constraints
        numeric_keys = ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"]
        for key in numeric_keys:
            if key in field and ftype not in ("integer", "number"):
                raise ParseError(
                    f"Field '{name}': '{key}' is only valid for integer/number types."
                )

        # minimum must be <= maximum
        if "minimum" in field and "maximum" in field:
            if field["minimum"] > field["maximum"]:
                raise ParseError(
                    f"Field '{name}': minimum ({field['minimum']}) "
                    f"must be <= maximum ({field['maximum']})."
                )

        # enum values must match type
        if "enum" in field:
            if not isinstance(field["enum"], list) or len(field["enum"]) == 0:
                raise ParseError(f"Field '{name}': enum must be a non-empty list.")
            for val in field["enum"]:
                if ftype == "integer" and not isinstance(val, int):
                    raise ParseError(
                        f"Field '{name}': enum value '{val}' is not an integer."
                    )
                if ftype == "string" and not isinstance(val, str):
                    raise ParseError(
                        f"Field '{name}': enum value '{val}' is not a string."
                    )

        # default must match type
        if "default" in field:
            default = field["default"]
            type_map = {
                "string":  str,
                "integer": int,
                "number":  (int, float),
                "boolean": bool,
            }
            if ftype in type_map:
                if not isinstance(default, type_map[ftype]):
                    raise ParseError(
                        f"Field '{name}': default value '{default}' "
                        f"does not match type '{ftype}'."
                    )

        # pattern only for strings
        if "pattern" in field and ftype != "string":
            raise ParseError(
                f"Field '{name}': 'pattern' is only valid for string types."
            )
