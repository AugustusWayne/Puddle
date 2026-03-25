import os
import yaml
from typing import Dict, Any


class LiteralStr(str):
    """Forces YAML to dump this string in literal block style."""
    pass


def _str_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(LiteralStr, _str_representer)


def write_manifests(
    crd: Dict[str, Any],
    cr: Dict[str, Any],
    output_dir: str,
    kind: str,
) -> tuple[str, str]:
    """
    Write CRD and CR manifests to output_dir.
    Returns (crd_path, cr_path).
    """
    os.makedirs(output_dir, exist_ok=True)

    crd_path = os.path.join(output_dir, f"{kind.lower()}-crd.yaml")
    cr_path  = os.path.join(output_dir, f"{kind.lower()}-cr-sample.yaml")

    with open(crd_path, "w") as f:
        yaml.dump(crd, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    with open(cr_path, "w") as f:
        yaml.dump(cr, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return crd_path, cr_path


def to_yaml_string(manifest: Dict[str, Any]) -> str:
    """Return a manifest as a clean YAML string (for web preview / stdout)."""
    return yaml.dump(manifest, default_flow_style=False, sort_keys=False, allow_unicode=True)
