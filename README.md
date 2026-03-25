<div align="center">

# ⎈ K8s Custom Resource Generator

**Stop writing Kubernetes CRD boilerplate. Define your resource in YAML, get production-ready manifests instantly.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-13%20passing-22c55e)](#testing)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-a855f7.svg)](CONTRIBUTING.md)

<br/>

<img src="https://img.shields.io/badge/Kubernetes-326CE5?logo=kubernetes&logoColor=white" alt="Kubernetes"/>
<img src="https://img.shields.io/badge/Flask-000000?logo=flask&logoColor=white" alt="Flask"/>
<img src="https://img.shields.io/badge/OpenAPI_v3-6BA539?logo=openapiinitiative&logoColor=white" alt="OpenAPI"/>

</div>

---

## The Problem

Creating Kubernetes Custom Resource Definitions is painful:

- **Verbose**: A simple CRD with 5 fields balloons into 70+ lines of deeply nested YAML
- **Error-prone**: One indentation mistake = broken schema the API server silently accepts until runtime
- **Repetitive**: Every CRD needs the same boilerplate — `apiVersion`, `openAPIV3Schema`, `subresources`, `additionalPrinterColumns`
- **No validation feedback**: You only discover schema mismatches when `kubectl apply` fails

## The Solution

Define your custom resource in a **simple, flat YAML config** — the generator handles the rest:

```yaml
# This is ALL you write:
resource:
  group: myapp.io
  version: v1alpha1
  kind: Database
  scope: Namespaced
  fields:
    - name: engine
      type: string
      required: true
      enum: [postgres, mysql, mongodb]
    - name: replicas
      type: integer
      required: true
      minimum: 1
      maximum: 10
```

**Output**: A complete, `kubectl apply`-ready CRD manifest with OpenAPI v3 validation schema, printer columns, status subresource, and a matching sample CR — all generated in milliseconds.

---

## Features

| Feature | Description |
|---------|-------------|
| 🔍 **Input validation** | Catches type mismatches, invalid constraints, and schema errors *before* you touch your cluster |
| 📐 **OpenAPI v3 schemas** | Generates full `openAPIV3Schema` with types, enums, min/max, defaults, patterns |
| 🖨️ **Printer columns** | Auto-generates `additionalPrinterColumns` so `kubectl get` shows useful data |
| 📄 **Sample CR** | Produces a valid sample CR with sensible defaults for quick testing |
| 🖥️ **CLI + Web UI** | Use the CLI for automation/CI or the web UI for interactive exploration |
| 🔌 **Pluggable engine** | Core generator has zero dependency on CLI or web — import it in your own tools |
| ✅ **13 unit tests** | Comprehensive test coverage for generators, validators, and edge cases |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Input                           │
│              (YAML file  /  Web form  /  API)               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  cli/main.py           │           web/app.py               │
│  (argparse CLI)        │           (Flask REST)              │
│  Thin interface shells — no business logic                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  generator/  (Core Engine)                   │
│                                                             │
│  parser.py ──► validator.py ──► schema_builder.py           │
│                                    │                        │
│                          ┌─────────┴──────────┐             │
│                          ▼                    ▼             │
│                   crd_generator.py     cr_generator.py      │
│                          │                    │             │
│                          └─────────┬──────────┘             │
│                                    ▼                        │
│                              writer.py                      │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Generated Output                         │
│         database-crd.yaml    database-cr-sample.yaml        │
└─────────────────────────────────────────────────────────────┘
```

> The core `generator/` package is a pure library with no I/O dependencies. Both the CLI and web UI are thin shells over it, meaning you can also `import generator` directly in your own Python scripts.

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/<your-username>/k8s-cr-generator.git
cd k8s-cr-generator

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Generate manifests

```bash
python generator.py --input examples/database-input.yaml --output ./output
```

### 3. Apply to your cluster

```bash
kubectl apply -f output/database-crd.yaml
kubectl get crd databases.myapp.io

kubectl apply -f output/database-cr-sample.yaml
kubectl get databases
```

---

## CLI Reference

```
python generator.py --input <file> [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--input` | `-i` | **(required)** Path to input YAML config |
| `--output` | `-o` | Output directory (default: `./output`) |
| `--name` | `-n` | Custom name for sample CR (default: `sample-<kind>`) |
| `--dry-run` | | Print YAML to stdout only, don't write files |
| `--stdout` | | Print YAML to stdout *and* write files |

### Examples

```bash
# Dry-run — preview without writing
python generator.py -i examples/database-input.yaml --dry-run

# Custom CR name + custom output dir
python generator.py -i examples/database-input.yaml -o ./manifests -n production-db

# Write files and also print to terminal
python generator.py -i examples/database-input.yaml --stdout
```

---

## Web UI

Start the Flask development server:

```bash
python web/app.py
# → http://localhost:5000
```

The web UI provides:
- A form to define your resource (group, version, kind, scope, fields)
- Dynamic field builder — add/remove fields with type, required, and default controls
- **Live YAML preview** with tabs for CRD and Sample CR
- Inline validation error display

### API Endpoint

```bash
curl -X POST http://localhost:5000/generate \
  -H "Content-Type: application/json" \
  -d @examples/database-input.yaml
```

Returns:
```json
{
  "crd_yaml": "apiVersion: apiextensions.k8s.io/v1\n...",
  "cr_yaml": "apiVersion: myapp.io/v1alpha1\n...",
  "errors": []
}
```

---

## Input YAML Reference

```yaml
resource:
  group: <string>          # API group (e.g. myapp.io)
  version: <string>        # API version (e.g. v1alpha1)
  kind: <string>           # PascalCase kind name (e.g. Database)
  scope: <Namespaced|Cluster>
  description: <string>    # Optional description

  fields:
    - name: <string>       # Field name (camelCase recommended)
      type: <string|integer|number|boolean|object|array>
      required: <bool>     # Default: false
      default: <any>       # Default value (must match type)
      enum: [<values>]     # Allowed values (must match type)
      minimum: <number>    # Min value (integer/number only)
      maximum: <number>    # Max value (integer/number only)
      pattern: <regex>     # Regex pattern (string only)
      description: <string>
```

### Validation Rules

The generator validates your input and gives clear errors:

- `minimum` / `maximum` only valid on `integer` and `number` types
- `minimum` must be ≤ `maximum`
- `enum` values must match the declared `type`
- `default` value must match the declared `type`
- `pattern` only valid on `string` type

---

## Project Structure

```
k8s-cr-generator/
├── generator.py                 # Top-level entry point
├── requirements.txt             # Dependencies
├── examples/
│   └── database-input.yaml      # Sample input config
├── generator/                   # Core engine (pure library)
│   ├── parser.py                # YAML loader + structural checks
│   ├── validator.py             # Deep field constraint validation
│   ├── schema_builder.py        # OpenAPI v3 schema assembler
│   ├── crd_generator.py         # Full CRD manifest builder
│   ├── cr_generator.py          # Sample CR manifest builder
│   └── writer.py                # YAML file writer
├── cli/
│   └── main.py                  # CLI entry point (argparse)
├── web/
│   ├── app.py                   # Flask web wrapper
│   └── templates/
│       └── index.html           # Web UI
└── tests/
    └── test_crd_generator.py    # Unit tests
```

---

## Testing

```bash
pytest tests/ -v
```

```
tests/test_crd_generator.py::TestCRDGenerator::test_crd_api_version       PASSED
tests/test_crd_generator.py::TestCRDGenerator::test_crd_name_format       PASSED
tests/test_crd_generator.py::TestCRDGenerator::test_crd_has_spec_schema   PASSED
tests/test_crd_generator.py::TestCRDGenerator::test_required_fields_present PASSED
tests/test_crd_generator.py::TestCRDGenerator::test_enum_preserved        PASSED
tests/test_crd_generator.py::TestCRDGenerator::test_subresource_status    PASSED
tests/test_crd_generator.py::TestCRDGenerator::test_printer_columns       PASSED
tests/test_crd_generator.py::TestCRGenerator::test_cr_api_version         PASSED
tests/test_crd_generator.py::TestCRGenerator::test_cr_uses_first_enum     PASSED
tests/test_crd_generator.py::TestCRGenerator::test_cr_default_value       PASSED
tests/test_crd_generator.py::TestValidator::test_min_gt_max_fails         PASSED
tests/test_crd_generator.py::TestValidator::test_pattern_non_string_fails PASSED
tests/test_crd_generator.py::TestValidator::test_wrong_enum_type_fails    PASSED

13 passed
```

---

## Contributing

Contributions are welcome! Here are some ways to help:

1. **Fork** the repo and create your branch from `main`
2. **Add tests** for any new functionality
3. **Run** `pytest tests/ -v` to ensure all tests pass
4. **Open a Pull Request** with a clear description

### Ideas for Contributions

- Add more example input configs (Redis, Message Queue, etc.)
- Support nested `object` and `array` field schemas
- Add `--format json` output option
- Generate RBAC manifests (Role, RoleBinding) alongside the CRD
- Helm chart template generation
- GitHub Actions CI pipeline
- Docker container for the web UI

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built by lazyduck**

[Report Bug](../../issues) · [Request Feature](../../issues) · [Contribute](CONTRIBUTING.md)

</div>
