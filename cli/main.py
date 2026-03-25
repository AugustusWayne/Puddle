import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator.parser      import load_input, ParseError
from generator.validator   import validate_fields
from generator.crd_generator import generate_crd
from generator.cr_generator  import generate_cr
from generator.writer       import write_manifests, to_yaml_string


def print_banner():
    print("\n╔══════════════════════════════════════╗")
    print("║   Kubernetes Custom Resource Generator  ║")
    print("╚══════════════════════════════════════╝\n")


def run_cli():
    parser = argparse.ArgumentParser(
        prog="k8s-crg",
        description="Generate Kubernetes CRD and CR manifests from a config file.",
    )
    parser.add_argument(
        "--input",  "-i",
        required=True,
        help="Path to input YAML config file (e.g. examples/database-input.yaml)",
    )
    parser.add_argument(
        "--output", "-o",
        default="./output",
        help="Directory to write generated manifests (default: ./output)",
    )
    parser.add_argument(
        "--name", "-n",
        default=None,
        help="Name for the sample CR (default: sample-<kind>)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print YAML to stdout only, do not write files",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Also print YAML to stdout after writing files",
    )

    args = parser.parse_args()
    print_banner()

    # 1. Parse
    print(f"[1/4] Parsing input:    {args.input}")
    try:
        resource = load_input(args.input)
    except ParseError as e:
        print(f"\n  ERROR: {e}")
        sys.exit(1)
    print(f"       Kind: {resource['kind']}  |  Group: {resource['group']}  |  Version: {resource['version']}")

    # 2. Validate
    print(f"[2/4] Validating {len(resource['fields'])} field(s)...")
    try:
        validate_fields(resource["fields"])
    except ParseError as e:
        print(f"\n  ERROR: {e}")
        sys.exit(1)
    print("       All fields valid.")

    # 3. Generate
    print("[3/4] Generating manifests...")
    crd = generate_crd(resource)
    cr  = generate_cr(resource, name=args.name)

    # 4. Write or dry-run
    if args.dry_run:
        print("[4/4] Dry-run mode — printing to stdout:\n")
        print("# ─── CRD ─────────────────────────────────")
        print(to_yaml_string(crd))
        print("# ─── Sample CR ───────────────────────────")
        print(to_yaml_string(cr))
    else:
        print(f"[4/4] Writing to:       {args.output}/")
        crd_path, cr_path = write_manifests(crd, cr, args.output, resource["kind"])
        print(f"       CRD:             {crd_path}")
        print(f"       Sample CR:       {cr_path}")

        if args.stdout:
            print("\n# ─── CRD ─────────────────────────────────")
            print(to_yaml_string(crd))
            print("# ─── Sample CR ───────────────────────────")
            print(to_yaml_string(cr))

    print("\nDone. Apply with:")
    print(f"  kubectl apply -f {args.output}/{resource['kind'].lower()}-crd.yaml")
    print(f"  kubectl apply -f {args.output}/{resource['kind'].lower()}-cr-sample.yaml\n")


if __name__ == "__main__":
    run_cli()
