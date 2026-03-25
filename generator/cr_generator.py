from typing import Dict, Any


def _sample_value(field: Dict[str, Any]) -> Any:
    """Pick a sensible sample value for a field."""
    if "default" in field:
        return field["default"]
    if "enum" in field:
        return field["enum"][0]

    ftype = field["type"]
    if ftype == "string":   return f"my-{field['name']}"
    if ftype == "integer":  return field.get("minimum", 1)
    if ftype == "number":   return field.get("minimum", 1.0)
    if ftype == "boolean":  return False
    if ftype == "object":   return {}
    if ftype == "array":    return []
    return None


def generate_cr(resource: Dict[str, Any], name: str = None) -> Dict[str, Any]:
    """
    Generate a sample CR manifest that conforms to the CRD spec.
    """
    kind    = resource["kind"]
    group   = resource["group"]
    version = resource["version"]
    fields  = resource["fields"]

    cr_name = name or f"sample-{kind.lower()}"

    spec = {
        field["name"]: _sample_value(field)
        for field in fields
    }

    cr = {
        "apiVersion": f"{group}/{version}",
        "kind":       kind,
        "metadata": {
            "name":      cr_name,
            "namespace": "default",
            "labels": {
                "app.kubernetes.io/managed-by": "k8s-cr-generator",
            },
        },
        "spec": spec,
    }
    return cr
