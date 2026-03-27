"""
writer.py
~~~~~~~~~
Writes generated manifests to disk or returns them as YAML strings.

Note: the YAML Dumper used here is a *fresh instance* (``yaml.Dumper``)
so the LiteralStr representer is NOT registered on the global yaml module,
avoiding unexpected side-effects in the hosting process.
"""

import os
import yaml
from typing import Any, Dict, Tuple


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

class LiteralStr(str):
    """Forces YAML to emit this string in ``|`` (literal block) style."""


def _make_dumper() -> type:
    """
    Return a Dumper subclass with the LiteralStr representer wired up.
    Creating a subclass each time keeps the global yaml state clean.
    """
    class _Dumper(yaml.Dumper):  # type: ignore[misc]
        pass

    def _literal_representer(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
        style = "|" if "\n" in data else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)

    _Dumper.add_representer(LiteralStr, _literal_representer)
    return _Dumper


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def to_yaml_string(manifest: Dict[str, Any]) -> str:
    """Serialise *manifest* to a clean YAML string."""
    return yaml.dump(
        manifest,
        Dumper=_make_dumper(),
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )


def write_manifests(
    crd: Dict[str, Any],
    cr: Dict[str, Any],
    output_dir: str,
    kind: str,
) -> Tuple[str, str]:
    """
    Write CRD and CR manifests to *output_dir*.

    Parameters
    ----------
    crd, cr:
        Manifest dicts as returned by the generator functions.
    output_dir:
        Directory path (will be created if it doesn't exist).
    kind:
        Resource kind string used to derive the output file names.

    Returns
    -------
    (crd_path, cr_path)
        Absolute paths to the files that were written.
    """
    os.makedirs(output_dir, exist_ok=True)

    crd_path = os.path.join(output_dir, f"{kind.lower()}-crd.yaml")
    cr_path  = os.path.join(output_dir, f"{kind.lower()}-cr-sample.yaml")

    dumper = _make_dumper()
    dump_kwargs = dict(Dumper=dumper, default_flow_style=False,
                       sort_keys=False, allow_unicode=True)

    with open(crd_path, "w", encoding="utf-8") as fh:
        yaml.dump(crd, fh, **dump_kwargs)

    with open(cr_path, "w", encoding="utf-8") as fh:
        yaml.dump(cr, fh, **dump_kwargs)

    return crd_path, cr_path
