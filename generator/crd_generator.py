"""
crd_generator.py
~~~~~~~~~~~~~~~~
Assembles a complete, kubectl-apply-ready CRD manifest from a validated
resource definition dict.  Follows the apiextensions.k8s.io/v1 spec.
"""

import re
from typing import Dict, Any

from .schema_builder import build_spec_schema, build_printer_columns


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pluralise(word: str) -> str:
    """
    Very small English pluralisation for PascalCase Kubernetes kind names.
    Handles the most common irregular endings; defaults to appending 's'.

    Examples
    --------
    Database     -> databases
    Index        -> indexes
    Policy       -> policies
    Redis        -> redises  (acceptable for k8s CRD plural names)
    MessageQueue -> messagequeues
    """
    w = word.lower()
    if w.endswith(("s", "x", "z", "ch", "sh")):
        return w + "es"
    if w.endswith("y") and len(w) > 1 and w[-2] not in "aeiou":
        return w[:-1] + "ies"
    return w + "s"


def _short_name(kind: str) -> str:
    """
    Derive a short, collision-resistant kubectl alias from a kind name.

    Strategy
    --------
    1. Split the kind into a letters-only base and a trailing digit suffix
       (e.g. ``Database2`` → base=``Database``, suffix=``2``).
    2. Take the first letter of the base.
    3. Find the first consonant *after* position 0 and append it.
    4. Append the digit suffix so numbered variants are distinct.

    Examples
    --------
    Database     -> db
    Database2    -> db2
    Redis        -> rd
    MessageQueue -> mq
    Policy       -> pl
    """
    match = re.match(r'^([A-Za-z]+?)(\d*)$', kind)
    if match:
        letters = match.group(1)
        digits  = match.group(2)
    else:
        # Fallback: strip all digits inline
        letters = re.sub(r'\d', '', kind) or kind
        digits  = "".join(c for c in kind if c.isdigit())

    vowels = set("aeiouAEIOU")
    first     = letters[0].lower()
    consonant = next(
        (c.lower() for c in letters[1:] if c not in vowels),
        letters[1].lower() if len(letters) > 1 else first,
    )
    return first + consonant + digits


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_crd(resource: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assemble a complete CRD manifest dict ready for ``kubectl apply``.

    Parameters
    ----------
    resource:
        Validated resource definition as returned by ``parser.load_input()``.

    Returns
    -------
    dict
        A Python dict that serialises to a valid ``apiextensions.k8s.io/v1``
        CustomResourceDefinition YAML manifest.
    """
    kind    = resource["kind"]
    group   = resource["group"]
    version = resource["version"]
    scope   = resource["scope"]
    fields  = resource["fields"]
    desc    = resource.get("description", f"Custom resource for {kind}")

    plural   = _pluralise(kind)
    singular = kind.lower()
    crd_name = f"{plural}.{group}"

    properties, required = build_spec_schema(fields)
    printer_columns      = build_printer_columns(fields)

    spec_schema: Dict[str, Any] = {
        "type":       "object",
        "properties": properties,
    }
    if required:
        spec_schema["required"] = required

    return {
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
                "shortNames": [_short_name(kind)],
            },
        },
    }
