from flask import Flask, request, jsonify, render_template
import sys, os, traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator.parser        import load_input, ParseError
from generator.validator     import validate_fields
from generator.crd_generator import generate_crd
from generator.cr_generator  import generate_cr
from generator.writer        import to_yaml_string

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    """
    Accepts JSON body matching the same schema as input.yaml.
    Returns { crd_yaml: "...", cr_yaml: "...", errors: [] }
    """
    data = request.get_json(force=True)

    if not data or "resource" not in data:
        return jsonify({"errors": ["Request body must contain a 'resource' key."]}), 400

    try:
        # Reuse the same validation pipeline as the CLI
        resource = data["resource"]

        # Minimal structural check (parser.load_input reads files;
        # for web we validate the dict directly)
        required_keys = ["group", "version", "kind", "scope", "fields"]
        for key in required_keys:
            if key not in resource:
                raise ParseError(f"Missing required field: resource.{key}")

        validate_fields(resource["fields"])

        crd = generate_crd(resource)
        cr  = generate_cr(resource)

        return jsonify({
            "crd_yaml": to_yaml_string(crd),
            "cr_yaml":  to_yaml_string(cr),
            "errors":   [],
        })

    except ParseError as e:
        return jsonify({"errors": [str(e)]}), 422
    except Exception:
        return jsonify({"errors": [traceback.format_exc()]}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
