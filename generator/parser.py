import yaml
import os
from typing import Dict, Any


VALID_TYPES   = {"string", "integer", "number", "boolean", "object", "array"}
VALID_SCOPES  = {"Namespaced", "Cluster"}

class ParseError(Exception):
    """Raised when the input config is invalid."""
    pass


def load_input(filepath: str) -> Dict[str, Any]:
    """Load and do a first-pass structural check on the input YAML."""
    if not os.path.exists(filepath):
        raise ParseError(f"Input file not found: {filepath}")

    with open(filepath, "r") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ParseError(f"YAML parse error: {e}")

    if not isinstance(data, dict) or "resource" not in data:
        raise ParseError("Input YAML must have a top-level 'resource' key.")

    resource = data["resource"]

    # Check required top-level fields
    required_keys = ["group", "version", "kind", "scope", "fields"]
    for key in required_keys:
        if key not in resource:
            raise ParseError(f"Missing required field: resource.{key}")

    if resource["scope"] not in VALID_SCOPES:
        raise ParseError(
            f"Invalid scope '{resource['scope']}'. Must be one of {VALID_SCOPES}"
        )

    if not isinstance(resource["fields"], list) or len(resource["fields"]) == 0:
        raise ParseError("resource.fields must be a non-empty list.")

    for i, field in enumerate(resource["fields"]):
        if "name" not in field:
            raise ParseError(f"Field at index {i} is missing 'name'.")
        if "type" not in field:
            raise ParseError(f"Field '{field['name']}' is missing 'type'.")
        if field["type"] not in VALID_TYPES:
            raise ParseError(
                f"Field '{field['name']}' has invalid type '{field['type']}'. "
                f"Valid types: {VALID_TYPES}"
            )

    return resource
