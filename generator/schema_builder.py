from typing import Dict, Any, List, Tuple


# Keys from the input that map 1-to-1 into OpenAPI v3 property keywords
PASSTHROUGH_KEYS = [
    "type", "enum", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum",
    "default", "description", "pattern",
]


def build_property(field: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a single field definition into an OpenAPI v3 property dict."""
    prop = {}
    for key in PASSTHROUGH_KEYS:
        if key in field:
            prop[key] = field[key]
    return prop


def build_spec_schema(fields: List[Dict[str, Any]]) -> Tuple[Dict, List[str]]:
    """
    Build the full spec.properties dict and required list.
    Returns (properties_dict, required_list).
    """
    properties = {}
    required   = []

    for field in fields:
        properties[field["name"]] = build_property(field)
        if field.get("required", False):
            required.append(field["name"])

    return properties, required


def build_printer_columns(fields: List[Dict[str, Any]]) -> List[Dict]:
    """
    Auto-generate additionalPrinterColumns for kubectl get output.
    Includes the first 3 required fields + Age by default.
    """
    type_map = {
        "string":  "string",
        "integer": "integer",
        "number":  "number",
        "boolean": "boolean",
    }
    columns = []
    count = 0
    for field in fields:
        if count >= 3:
            break
        columns.append({
            "name":     field["name"].capitalize(),
            "type":     type_map.get(field["type"], "string"),
            "jsonPath": f".spec.{field['name']}",
        })
        count += 1

    # Always add Age
    columns.append({
        "name":     "Age",
        "type":     "date",
        "jsonPath": ".metadata.creationTimestamp",
    })
    return columns
