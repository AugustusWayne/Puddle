# K8s Custom Resource Generator — Detailed Project Report

## 1. Executive Summary

The **Kubernetes Custom Resource Generator** (k8s-crg) is a Python-based tool that automates the creation of Kubernetes Custom Resource Definition (CRD) and Custom Resource (CR) manifests from a simple, human-writable YAML configuration file.

Instead of manually crafting 70+ lines of deeply nested YAML with OpenAPI v3 schemas, users define their resource in a flat 15–20 line config. The tool handles structural validation, type checking, schema generation, printer column setup, and manifest output — producing production-ready files that can be directly applied with `kubectl apply`.

The project ships with both a CLI interface for automation/CI pipelines and a Flask-based web UI for interactive exploration, both built on a shared, import-friendly core engine.

---

## 2. Problem Statement

### Why Kubernetes CRDs Are Hard to Write by Hand

Kubernetes Custom Resource Definitions (CRDs) are the standard mechanism for extending the Kubernetes API. They allow platform teams to define new resource types — databases, queues, certificates, anything — that behave like native Kubernetes objects.

However, writing CRDs by hand is problematic:

| Challenge | Impact |
|-----------|--------|
| **Deep nesting** | CRD schemas require 5–7 levels of YAML indentation. A single misplaced space breaks the manifest. |
| **OpenAPI v3 boilerplate** | Every field needs explicit type declarations, wrapped in `openAPIV3Schema.properties.spec.properties` — verbose and repetitive. |
| **No inline validation** | YAML editors don't validate CRD schemas. Errors surface only at `kubectl apply` time, or worse, at CR creation time. |
| **Missing convenience features** | Printer columns (`kubectl get` output), status subresources, and short names all require additional boilerplate that's easy to forget. |
| **No sample CR generation** | After writing a CRD, you still need to manually create a matching CR for testing. |

### Who This Helps

- **Platform engineers** building internal developer platforms with custom Kubernetes resources
- **DevOps teams** standardizing infrastructure-as-code with CRDs
- **Students and learners** exploring Kubernetes custom resources without getting lost in YAML syntax
- **CI/CD pipelines** that need to generate CRDs programmatically from a config source of truth

---

## 3. Technical Architecture

### Design Philosophy

The project follows three principles:

1. **Separation of concerns**: The core engine (`generator/`) has zero knowledge of how it's invoked. The CLI and web UI are thin shells.
2. **Fail early, fail clearly**: Input validation happens in two stages (structural + semantic) before any generation, with human-readable error messages.
3. **Import-friendly**: The `generator` package can be imported directly into other Python projects — no CLI or Flask dependency required.

### Module Pipeline

```
Input YAML
    │
    ▼
parser.py          ──►  Load file, check structure, validate types/scope
    │
    ▼
validator.py       ──►  Cross-validate field constraints against types
    │
    ▼
schema_builder.py  ──►  Convert fields → OpenAPI v3 properties + required list
    │                    Generate additionalPrinterColumns
    │
    ├──► crd_generator.py  ──►  Assemble full apiextensions.k8s.io/v1 CRD
    │
    └──► cr_generator.py   ──►  Generate sample CR with sensible defaults
              │
              ▼
         writer.py         ──►  Write YAML to disk or return as string
```

### Module Details

#### `generator/parser.py`
- Loads the input YAML file using `pyyaml`
- Validates top-level structure: `group`, `version`, `kind`, `scope`, `fields` must all be present
- Checks `scope` is one of `Namespaced` or `Cluster`
- Validates each field has `name` and `type`, and that `type` is in the allowed set: `string`, `integer`, `number`, `boolean`, `object`, `array`
- Raises `ParseError` with descriptive messages on any failure

#### `generator/validator.py`
- Performs deep semantic validation of field constraints:
  - `minimum`/`maximum` only allowed on numeric types
  - `minimum ≤ maximum` check
  - `enum` values must match the declared field type
  - `default` values must match the declared field type
  - `pattern` only allowed on string types
- This layer catches subtle bugs that would otherwise only surface at Kubernetes API server time

#### `generator/schema_builder.py`
- Converts the flat field list into OpenAPI v3 `properties` dicts
- Separates required vs. optional fields into the `required` list
- Auto-generates `additionalPrinterColumns` from the first 3 fields + an Age column
- Uses a passthrough key list (`type`, `enum`, `minimum`, `maximum`, `default`, `description`, `pattern`, etc.) for clean 1:1 mapping

#### `generator/crd_generator.py`
- Assembles the complete `apiextensions.k8s.io/v1` CRD manifest including:
  - `openAPIV3Schema` with the generated spec schema
  - `status` subresource with `x-kubernetes-preserve-unknown-fields`
  - `additionalPrinterColumns` for `kubectl get` output
  - Auto-generated `names` (plural, singular, shortNames)
  - Metadata annotations (`generated-by: k8s-cr-generator`)

#### `generator/cr_generator.py`
- Generates a sample CR that conforms to the generated CRD
- Picks sensible values: defaults if specified, first enum value if available, type-appropriate placeholders otherwise
- Includes standard metadata: namespace, labels with `managed-by`

#### `generator/writer.py`
- Writes CRD and CR manifests to disk as clean YAML files
- Provides `to_yaml_string()` for stdout/web preview
- Custom YAML representer for literal block style on multi-line strings

### Interface Layers

#### CLI (`cli/main.py`)
- Thin argparse wrapper with progress output (`[1/4]`, `[2/4]`, etc.)
- Supports `--dry-run`, `--stdout`, `--output`, `--name`
- Exit code 1 on validation errors for CI integration

#### Web UI (`web/app.py` + `web/templates/index.html`)
- Flask app with a single `/generate` POST endpoint
- Accepts the same JSON structure as the input YAML
- Returns `{ crd_yaml, cr_yaml, errors }` JSON response
- Frontend: dark-themed SPA with dynamic field builder, live YAML preview, tabbed CRD/CR output

---

## 4. Design Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| **Flat input format** (not nested OpenAPI) | Prioritized human-writability over expressiveness. Power users can extend the generator; most users need simple field lists. |
| **Two-stage validation** (parser + validator) | Structural errors (missing keys) are caught immediately. Semantic errors (type mismatches) are caught in a second pass, producing better error messages. |
| **Passthrough key design** in schema_builder | Any OpenAPI v3 keyword in the input passes directly to the output. This makes the tool forward-compatible — new OpenAPI keywords work without code changes. |
| **Auto-generated printer columns** | Users rarely remember to add these, but they dramatically improve `kubectl get` output. Generating them automatically is a UX win. |
| **Short names from first 2 chars** | `Database` → `da`, `MessageQueue` → `me`. A reasonable default that users can override in the generated YAML. |
| **No Kubernetes client dependency** | The tool generates static YAML files. It never talks to a cluster, keeping it simple, fast, and usable offline. |
| **Flask over FastAPI** | Simpler for a tool this size. No async needed, minimal endpoints. Flask's template rendering is also used for the web UI. |

---

## 5. Testing Strategy

### Test Coverage

The test suite covers three areas:

| Test Class | Tests | What's Tested |
|------------|-------|---------------|
| `TestCRDGenerator` | 7 | API version, CRD naming format, spec schema presence, required field extraction, enum preservation, status subresource, printer columns |
| `TestCRGenerator` | 3 | CR API version format, first-enum-value selection, default value propagation |
| `TestValidator` | 3 | min > max rejection, pattern-on-non-string rejection, wrong-enum-type rejection |

### Running Tests

```bash
source venv/bin/activate
pytest tests/ -v
```

All 13 tests pass consistently on Python 3.10+.

---

## 6. Generated Output Example

### Input (15 lines)
```yaml
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

### Output CRD (73 lines)
A complete `apiextensions.k8s.io/v1` CRD with:
- Full `openAPIV3Schema` with type, enum, min, max constraints
- `required: [engine, replicas]`
- `additionalPrinterColumns` for Engine, Replicas, and Age
- `status` subresource enabled
- Auto-generated plural/singular/shortNames

### Output Sample CR (12 lines)
A valid `myapp.io/v1alpha1 Database` resource with:
- `engine: postgres` (first enum value)
- `replicas: 1` (minimum value)
- Standard metadata with namespace and labels

---

## 7. Future Roadmap

| Priority | Feature | Description |
|----------|---------|-------------|
| 🔴 High | **Nested object/array support** | Allow fields of type `object` and `array` to define their own sub-schemas |
| 🔴 High | **Multiple version support** | Generate CRDs with multiple versions and conversion webhooks |
| 🟡 Medium | **RBAC generation** | Auto-generate Role, ClusterRole, and RoleBinding manifests |
| 🟡 Medium | **Helm chart output** | Generate Helm chart templates instead of raw YAML |
| 🟡 Medium | **JSON output format** | `--format json` flag for JSON manifests |
| 🟢 Low | **Validation webhook scaffold** | Generate a validation webhook server skeleton |
| 🟢 Low | **Docker image** | Published container image for the web UI |
| 🟢 Low | **GitHub Actions CI** | Automated testing and release pipeline |

---

## 8. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| PyYAML | ≥ 6.0 | YAML parsing and generation |
| Flask | ≥ 3.0 | Web UI and REST API |
| pytest | ≥ 8.0 | Unit testing framework |

No Kubernetes client libraries are required. The tool generates static YAML files only.

---

## 9. Conclusion

The Kubernetes Custom Resource Generator solves a real, everyday pain point for platform engineers. By reducing CRD creation from a manual, error-prone process to a simple config-driven pipeline, it:

- **Saves time** — 5-field CRDs generated in milliseconds vs. 15–30 minutes by hand
- **Eliminates errors** — Two-stage validation catches issues before they reach the cluster
- **Standardizes output** — Every generated CRD follows best practices (subresources, printer columns, annotations)
- **Stays simple** — No cluster access needed, no heavy dependencies, import-friendly core

The clean separation between the core engine and interface layers means the tool can grow to support new output formats, deeper schemas, and CI/CD integrations without architectural changes.
