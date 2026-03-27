# K8s Custom Resource Generator — In-Depth Technical Report

> **Version:** post-cleanup (open-source release)
> **Tests:** 42 passing
> **Python:** 3.10+

---

## Table of Contents

1. [What the project does](#1-what-the-project-does)
2. [Why it exists — the real problem](#2-why-it-exists)
3. [Full data-flow walkthrough](#3-full-data-flow-walkthrough)
4. [Module-by-module deep dive](#4-module-by-module-deep-dive)
5. [The Web UI and Apply-to-Cluster feature](#5-the-web-ui-and-apply-to-cluster)
6. [Bugs fixed in the cleanup pass](#6-bugs-fixed-in-the-cleanup-pass)
7. [Test strategy](#7-test-strategy)
8. [How to contribute](#8-how-to-contribute)
9. [Future roadmap](#9-future-roadmap)

---

## 1. What the project does

The **K8s Custom Resource Generator** takes a short, human-writable YAML
config file and produces two fully-formed Kubernetes manifests:

| Output | What it is |
|--------|-----------|
| `<kind>-crd.yaml` | A `apiextensions.k8s.io/v1` CRD with a full OpenAPI v3 validation schema |
| `<kind>-cr-sample.yaml` | A matching sample Custom Resource instance ready to `kubectl apply` |

It ships with **two interfaces** over the same engine:

- **CLI** — `python generator.py --input … --output …` for automation and CI/CD
- **Web UI** — `python web/app.py` → `http://localhost:5000` for interactive use,
  with a live YAML preview and an **"Apply to Cluster"** button that runs the
  full `kubectl` sequence in the background

---

## 2. Why it exists

### The boilerplate problem

Writing a Kubernetes CRD by hand for even a simple 5-field resource
requires 70+ lines of deeply nested YAML.
The user must know the OpenAPI v3 vocabulary, the `apiextensions.k8s.io/v1`
schema shape, how `additionalPrinterColumns` work, how status subresources
are declared — all before they can think about what their resource actually
*does*.

A single indentation error silently passes YAML parsing but fails at
`kubectl apply` time. A type mismatch between an enum value and the
declared field type goes undetected until a CR is rejected at creation time.

### What this tool changes

```
User writes (15 lines):         Tool generates (~73 lines):
────────────────────────        ────────────────────────────
resource:                       apiVersion: apiextensions.k8s.io/v1
  group: myapp.io               kind: CustomResourceDefinition
  version: v1alpha1             metadata:
  kind: Database                  name: databases.myapp.io
  scope: Namespaced               annotations:
  fields:                           generated-by: k8s-cr-generator
    - name: engine              spec:
      type: string                group: myapp.io
      required: true              versions:
      enum: [postgres,mysql]       - name: v1alpha1
    - name: replicas               ...openAPIV3Schema...
      type: integer               ...additionalPrinterColumns...
      required: true              ...subresources...
      minimum: 1                  names:
      maximum: 10                   plural: databases
                                    singular: database
                                    shortNames: [dt]
```

The user expresses *intent*. The tool produces *compliant boilerplate*.

---

## 3. Full data-flow walkthrough

```
┌─────────────────────────────────────────────────────────┐
│                    User Entry Points                    │
│                                                         │
│  python generator.py --input file.yaml --output ./out   │
│              OR                                         │
│  POST http://localhost:5000/generate  { resource: … }   │
└──────────────────────┬──────────────────────────────────┘
                       │ dict: { group, version, kind,
                       │        scope, fields[] }
                       ▼
┌──────────────────────────────────────────────────────────┐
│  generator/parser.py  →  load_input(filepath)            │
│                                                          │
│  • Opens and yaml.safe_load() the file                   │
│  • Checks top-level 'resource' key exists                │
│  • Validates required keys: group, version, kind,        │
│    scope, fields                                         │
│  • Validates scope ∈ {Namespaced, Cluster}               │
│  • Validates each field has 'name' and a valid 'type'    │
│  • Raises ParseError immediately on any failure          │
└──────────────────────┬───────────────────────────────────┘
                       │ resource dict (clean)
                       ▼
┌──────────────────────────────────────────────────────────┐
│  generator/validator.py  →  validate_fields(fields)      │
│                                                          │
│  • minimum/maximum only on integer/number types          │
│  • minimum <= maximum                                    │
│  • enum is a non-empty list whose values match the type  │
│  • default value's Python type matches the field type    │
│  • pattern only on string types                          │
│  • Raises ParseError with precise field-level messages   │
└──────────────┬─────────────────────────┬─────────────────┘
               │                         │
               ▼                         ▼
┌─────────────────────────┐  ┌──────────────────────────────┐
│  generator/             │  │  generator/                  │
│  crd_generator.py       │  │  cr_generator.py             │
│                         │  │                              │
│  build_spec_schema()    │  │  _sample_value() picks:      │
│   → properties dict     │  │    1. field default          │
│   → required[] list     │  │    2. first enum value       │
│                         │  │    3. type-based placeholder │
│  build_printer_columns()│  │                              │
│   → first 3 fields      │  │  Outputs a valid CR with     │
│     + Age column        │  │  metadata, labels, spec      │
│                         │  │                              │
│  _pluralise(kind)       │  │                              │
│  _short_name(kind)      │  │                              │
│                         │  │                              │
│  Returns full CRD dict  │  │  Returns CR dict             │
└─────────┬───────────────┘  └──────────────┬───────────────┘
          │                                 │
          └──────────────┬──────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│  generator/writer.py                                     │
│                                                          │
│  to_yaml_string(manifest)                                │
│    → yaml.dump() using a fresh Dumper subclass           │
│      (does NOT mutate global yaml state)                 │
│                                                          │
│  write_manifests(crd, cr, output_dir, kind)              │
│    → creates output_dir if needed                        │
│    → writes <kind>-crd.yaml                              │
│    → writes <kind>-cr-sample.yaml                        │
│    → returns (crd_path, cr_path)                         │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Module-by-module deep dive

### `generator/parser.py`

**Role:** Structural validation. Is the input file readable and does it have
the right shape?

**Key design decision:** The `ParseError` exception class lives here and is
imported by every other module. This keeps error handling uniform: all
validation failures across the entire pipeline surface as the same exception
type, which both the CLI and web layer catch in a single `except` block.

**What it does NOT do:** It doesn't check whether field constraints are
semantically valid (e.g. min > max). That is intentionally the validator's job,
keeping each module focused.

---

### `generator/validator.py`

**Role:** Semantic validation. Are the field constraints internally consistent?

The validator runs in a separate pass after parsing so that the error messages
can be field-specific and context-rich. If the parser and validator were merged,
the error messages would be harder to localise.

**Validation rules:**
| Rule | Example violation |
|------|-----------------|
| numeric constraints on numeric types only | `pattern` on `integer` |
| `minimum ≤ maximum` | `min: 10, max: 5` |
| enum values match declared type | `enum: [1,2]` on `string` |
| default matches declared type | `default: "hello"` on `integer` |
| `pattern` on `string` only | `pattern: "…"` on `boolean` |

---

### `generator/schema_builder.py`

**Role:** Convert the flat field list into OpenAPI v3 data structures.

**The passthrough key design** is the most important architectural decision
in this module. Instead of hand-mapping every possible OpenAPI keyword,
a `PASSTHROUGH_KEYS` list defines which keys copy directly from input to output:

```python
PASSTHROUGH_KEYS = [
    "type", "enum", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum",
    "default", "description", "pattern",
]
```

This means:
1. Any OpenAPI v3 keyword in the passthrough list works automatically
2. Adding support for a new keyword (e.g. `multipleOf`) is a one-line change
3. The module is forward-compatible with future OpenAPI extensions

**`build_printer_columns`** automatically creates `additionalPrinterColumns`
from the first 3 fields plus a mandatory Age column. This is the feature users
most often forget when writing CRDs by hand, and it makes `kubectl get` output
immediately useful.

---

### `generator/crd_generator.py`

**Role:** Assemble the final CRD dict.

**`_pluralise(kind)`** — proper English pluralisation for Kubernetes resource
plural names. The original code only appended `s`, which produced `indexs`,
`policys`, `watchs` etc. The fixed version handles the most common patterns:

```
Regular:  Database  → databases
-s/-x/-z: Index     → indexes,  Redis → redises
-ch/-sh:  Watch     → watches
-y (cons):Policy    → policies
-y (vowel):Monkey   → monkeys   (just +s)
```

**`_short_name(kind)`** — produces a 2-char kubectl alias. Strategy: first
letter + first consonant after it, optionally suffixed with any trailing
digit from the kind name. This makes numbered variants (`Database`, `Database2`)
produce distinct short names (`dt`, `dt2`), preventing the `ShortNamesConflict`
error that was breaking `kubectl wait` earlier.

---

### `generator/writer.py`

**Role:** Serialise manifests to YAML and write to disk.

**The global state bug (fixed):** The original code called
`yaml.add_representer(LiteralStr, _str_representer)` at module import time.
This mutated the global `yaml.Dumper` for the entire Python process — meaning
any other code using `yaml.dump()` in the same process would unexpectedly get
the `LiteralStr` behaviour. The fix creates a fresh `Dumper` *subclass* for
each call:

```python
# Before (bad — mutates global state):
yaml.add_representer(LiteralStr, _str_representer)
yaml.dump(data)

# After (clean — scoped to this call only):
class _Dumper(yaml.Dumper): pass
_Dumper.add_representer(LiteralStr, _literal_representer)
yaml.dump(data, Dumper=_Dumper)
```

---

### `cli/main.py`

**Role:** Thin argparse shell. Zero business logic.

The CLI's only job is to:
1. Parse command-line arguments
2. Call `load_input()` → `validate_fields()` → `generate_crd()` → `generate_cr()` → `write_manifests()`
3. Print progress output and exit with code 1 on any error

The exit code 1 on failure is what makes this CI/CD-friendly. A GitHub Actions
step running `python generator.py …` will fail the pipeline if the input config
is invalid.

---

### `web/app.py`

**Role:** Thin Flask shell. Same engine, HTTP interface.

**`/generate` (POST)** — the main generation endpoint. Accepts the resource
definition as JSON, runs the full pipeline, returns `{ crd_yaml, cr_yaml, errors }`.

**`/apply` (POST)** — the new "Apply to Cluster" endpoint. After generating
the manifests, it runs three `kubectl` commands in sequence:

```
Step 1: kubectl apply -f -   ← pipe CRD YAML into stdin
Step 2: kubectl wait --for=condition=Established crd/<name> --timeout=30s
Step 3: kubectl apply -f -   ← pipe CR YAML into stdin
```

The `wait` step between 1 and 3 is critical. Without it, step 3 fails with
`no matches for kind` because the Kubernetes API server hasn't finished
registering the new CRD type yet. This was the exact bug that failed during
the live demo.

The endpoint returns all three steps' stdout/stderr so the browser can render
a live terminal view.

**Error handling hierarchy:**
- `ParseError` → 422 Unprocessable Entity
- `subprocess.TimeoutExpired` → 504 Gateway Timeout
- `FileNotFoundError` (kubectl not on PATH) → 500 with helpful message
- Any other exception → 500 with full traceback

---

### `web/templates/index.html`

**Role:** Single-page web UI.

**Key features:**
- Dynamic field builder — rows are added/removed from the DOM without a page reload
- `collectFields()` coerces default values to the correct JavaScript type
  (`parseInt`, `parseFloat`, boolean) before sending JSON — previously all
  defaults were sent as strings
- "Apply to Cluster" button is *disabled* until YAML has been successfully generated,
  preventing users from applying stale or empty manifests
- Each kubectl step is rendered as a colour-coded line in a terminal-style div:
  - `t-cmd` (cyan) — the actual command that ran
  - `t-ok` (green) — successful stdout
  - `t-err` (red) — stderr or failure output
  - `t-info` (blue) — status messages from the browser

---

## 5. The Web UI and Apply-to-Cluster

### How Apply-to-Cluster works end-to-end

```
Browser                     Flask (/apply)              System
───────                     ──────────────              ──────
Click button
  │
  ├─ POST /apply ─────────►
  │   { resource: … }
  │                         _parse_resource()
  │                         validate_fields()
  │                         generate_crd() → crd_yaml
  │                         generate_cr()  → cr_yaml
  │
  │                         subprocess.run(
  │                           ['kubectl','apply','-f','-'],
  │                           input=crd_yaml             ──► API Server
  │                         )                           ◄── CRD created
  │
  │                         subprocess.run(
  │                           ['kubectl','wait',          ──► API Server
  │                            '--for=condition=Established',
  │                            'crd/<name>','--timeout=30s']
  │                         )                           ◄── Established ✓
  │
  │                         subprocess.run(
  │                           ['kubectl','apply','-f','-'],
  │                           input=cr_yaml              ──► API Server
  │                         )                           ◄── CR created ✓
  │
  │◄─ { steps: […], errors: [] }
  │
  Render terminal output
```

### Prerequisites for Apply-to-Cluster

- `kubectl` must be installed and on `$PATH`
- A cluster must be configured in `~/.kube/config` (Docker Desktop, Minikube,
  Kind, or a remote cluster)
- For cluster-scoped resources, appropriate RBAC permissions are needed

---

## 6. Bugs fixed in the cleanup pass

| # | Bug | Location | Fix |
|---|-----|----------|-----|
| 1 | `_pluralise` only appended `s` — `Index` → `indexs` | `crd_generator.py` | Added proper English plural rules |
| 2 | `_short_name` regex was non-greedy `+?` — `Database` → `D`+`a`+... | `crd_generator.py` | Fixed to greedy `+`; added digit suffix splitting |
| 3 | Dead `else` branch in `_short_name` | `crd_generator.py` | Cleaned up; now correctly handles all inputs |
| 4 | `yaml.add_representer` mutated global Dumper | `writer.py` | Now uses a fresh `Dumper` subclass per call |
| 5 | Duplicate structural validation in CLI and web | `web/app.py` | Extracted into shared `_parse_resource()` |
| 6 | All field defaults sent as strings from the web form | `index.html` | `collectFields()` now coerces to int/float/bool |
| 7 | No `kubectl wait` between CRD and CR apply | `web/app.py` | Added `kubectl wait --for=condition=Established` |

---

## 7. Test strategy

### Coverage

```
TestPluralise  (6)   database/redis/index/policy/monkey/watch
TestShortName  (6)   database/database2/redis/single-char/no-digit/digit-preserved
TestCRDGenerator (11) apiVersion/name/schema/required/enum/subresource/columns/
                       shortName/numbered-unique/index-plural/policy-plural
TestCRGenerator  (7)  apiVersion/enum/default/minimum/custom-name/default-name/label
TestValidator    (6)  min>max/pattern-nonstring/wrong-enum/min-on-string/
                       bad-default/valid-pass
TestWriter       (2)  yaml-string-type/contains-apiVersion
TestWebApp       (4)  index-200/valid-generate/missing-key/invalid-field-422

Total: 42 tests
```

### Running tests

```bash
source venv/bin/activate
pytest tests/ -v
```

### Philosophy

Tests are split by module responsibility, not by input/output shape.
Each test has one assertion (or a tightly related pair) so failures
point directly at the broken behaviour.

---

## 8. How to contribute

```bash
git clone https://github.com/AugustusWayne/Devops_project.git
cd Devops_project
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v          # make sure baseline is green
```

Good first contributions:
- Add more example input YAML files (`examples/redis-input.yaml`, etc.)
- Add `--format json` output flag to the CLI
- Support nested `object` fields with their own sub-schemas
- Generate RBAC manifests (Role + RoleBinding) alongside the CRD

Please run the full test suite and add tests for any new functionality
before opening a Pull Request.

---

## 9. Future roadmap

| Priority | Feature |
|----------|---------|
| 🔴 High | Nested `object`/`array` field sub-schemas |
| 🔴 High | Multiple API version support with conversion webhooks |
| 🟡 Medium | RBAC generation (Role, ClusterRole, RoleBinding) |
| 🟡 Medium | Helm chart template output |
| 🟡 Medium | `--format json` flag |
| 🟢 Low | Validation webhook server skeleton generation |
| 🟢 Low | Docker image for the web UI |
| 🟢 Low | GitHub Actions CI with automated test + release |
