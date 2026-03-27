"""
web/app.py
~~~~~~~~~~
Thin Flask wrapper around the k8s-cr-generator core engine.

Endpoints
---------
GET  /          Serve the web UI.
POST /generate  Validate + generate CRD/CR manifests; return YAML strings.
POST /apply     Generate manifests AND apply them to the local cluster via
                kubectl.  Returns step-by-step kubectl output so the browser
                can render a live terminal view.
"""

import os
import sys
import subprocess
import tempfile
import traceback

from flask import Flask, jsonify, render_template, request

# Make the project root importable when this file is run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator.parser        import ParseError
from generator.validator     import validate_fields
from generator.crd_generator import generate_crd
from generator.cr_generator  import generate_cr
from generator.writer        import to_yaml_string

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = ["group", "version", "kind", "scope", "fields"]


def _parse_resource(data: dict) -> dict:
    """
    Extract and minimally validate the ``resource`` dict from a JSON payload.
    Raises ParseError with a descriptive message on any structural problem.
    """
    if not data or "resource" not in data:
        raise ParseError("Request body must contain a 'resource' key.")

    resource = data["resource"]
    for key in _REQUIRED_KEYS:
        if key not in resource:
            raise ParseError(f"Missing required field: resource.{key}")

    if not isinstance(resource.get("fields"), list) or not resource["fields"]:
        raise ParseError("resource.fields must be a non-empty list.")

    return resource


def _kubectl(*args: str, stdin: str | None = None) -> dict:
    """
    Run a kubectl sub-command and return a dict with stdout, stderr, and
    returncode.  Never raises; the caller decides how to handle failures.
    """
    cmd = ["kubectl", *args]
    result = subprocess.run(
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=45,
    )
    return {
        "cmd":        " ".join(cmd),
        "stdout":     result.stdout.strip(),
        "stderr":     result.stderr.strip(),
        "returncode": result.returncode,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    """
    Body: ``{ resource: { group, version, kind, scope, fields, description? } }``

    Returns
    -------
    ``{ crd_yaml, cr_yaml, errors }``
    """
    try:
        resource = _parse_resource(request.get_json(force=True) or {})
        validate_fields(resource["fields"])
        crd = generate_crd(resource)
        cr  = generate_cr(resource)
        return jsonify({
            "crd_yaml": to_yaml_string(crd),
            "cr_yaml":  to_yaml_string(cr),
            "errors":   [],
        })
    except ParseError as exc:
        return jsonify({"errors": [str(exc)]}), 422
    except Exception:
        return jsonify({"errors": [traceback.format_exc()]}), 500


@app.route("/apply", methods=["POST"])
def apply_to_cluster():
    """
    Generate the manifests **and** apply them to the locally configured
    Kubernetes cluster using ``kubectl apply``.

    The CRD is applied first; the server then waits for it to reach
    ``Established`` state before applying the sample CR — avoiding the
    race condition where the CR lands before the API type is registered.

    Body: same JSON payload as ``/generate``.

    Returns
    -------
    ``{ steps: [ { cmd, stdout, stderr, returncode }, ... ], errors: [] }``
    """
    steps: list[dict] = []

    try:
        resource = _parse_resource(request.get_json(force=True) or {})
        validate_fields(resource["fields"])
        crd = generate_crd(resource)
        cr  = generate_cr(resource)

        crd_yaml = to_yaml_string(crd)
        cr_yaml  = to_yaml_string(cr)

        # Derive the CRD name for the wait command
        kind    = resource["kind"]
        group   = resource["group"]
        from generator.crd_generator import _pluralise
        plural   = _pluralise(kind)
        crd_name = f"{plural}.{group}"

        # Step 1: apply CRD
        step1 = _kubectl("apply", "-f", "-", stdin=crd_yaml)
        steps.append(step1)
        if step1["returncode"] != 0:
            return jsonify({"steps": steps, "errors": [step1["stderr"]]}), 500

        # Step 2: wait for CRD to be Established
        step2 = _kubectl(
            "wait", "--for=condition=Established",
            f"crd/{crd_name}", "--timeout=30s",
        )
        steps.append(step2)
        if step2["returncode"] != 0:
            return jsonify({"steps": steps, "errors": [step2["stderr"]]}), 500

        # Step 3: apply sample CR
        step3 = _kubectl("apply", "-f", "-", stdin=cr_yaml)
        steps.append(step3)
        if step3["returncode"] != 0:
            return jsonify({"steps": steps, "errors": [step3["stderr"]]}), 500

        return jsonify({"steps": steps, "errors": []})

    except ParseError as exc:
        return jsonify({"steps": steps, "errors": [str(exc)]}), 422
    except subprocess.TimeoutExpired:
        return jsonify({"steps": steps, "errors": ["kubectl timed out after 45 s."]}), 504
    except FileNotFoundError:
        return jsonify({
            "steps": steps,
            "errors": ["kubectl not found. Make sure it is installed and on your PATH."],
        }), 500
    except Exception:
        return jsonify({"steps": steps, "errors": [traceback.format_exc()]}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
