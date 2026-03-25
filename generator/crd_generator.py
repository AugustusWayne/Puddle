from typing import Dict, Any
from .schema_builder import build_spec_schema, build_printer_columns


def generate_crd(resource: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assemble a complete, kubectl-apply-ready CRD manifest.
    Follows the apiextensions.k8s.io/v1 spec.
    """
    kind     = resource["kind"]
    group    = resource["group"]
    version  = resource["version"]
    scope    = resource["scope"]
    fields   = resource["fields"]
    desc     = resource.get("description", f"Custom resource for {kind}")

    plural   = kind.lower() + "s"
    singular = kind.lower()
    crd_name = f"{plural}.{group}"

    properties, required = build_spec_schema(fields)
    printer_columns      = build_printer_columns(fields)

    spec_schema = {
        "type": "object",
        "properties": properties,
    }
    if required:
        spec_schema["required"] = required

    crd = {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind":       "CustomResourceDefinition",
        "metadata": {
            "name": crd_name,
            "annotations": {
                "generated-by": "k8s-cr-generator",
            },
        },
        "spec": {
            "group": group,
            "versions": [
                {
                    "name":    version,
                    "served":  True,
                    "storage": True,
                    "schema": {
                        "openAPIV3Schema": {
                            "type":        "object",
                            "description": desc,
                            "properties": {
                                "spec": spec_schema,
                                "status": {
                                    "type": "object",
                                    "x-kubernetes-preserve-unknown-fields": True,
                                },
                            },
                        }
                    },
                    "subresources": {
                        "status": {}
                    },
                    "additionalPrinterColumns": printer_columns,
                }
            ],
            "scope": scope,
            "names": {
                "plural":     plural,
                "singular":   singular,
                "kind":       kind,
                "shortNames": [kind[:2].lower()],  # e.g. "db" for Database
            },
        },
    }
    return crd
