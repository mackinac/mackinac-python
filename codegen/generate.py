#!/usr/bin/env python
"""generate.py — regenerate Pydantic v2 models from the JSON Schemas and OpenAPI spec.

Run this script whenever docs/api/schemas/ or docs/api/openapi.yaml changes.
The output files are committed to source control.

Usage (from mackinac-python/ root):
    pip install 'mackinac-client[dev]'
    python codegen/generate.py

Requirements:
    datamodel-code-generator >= 0.25
    Path to mackinac-web must be set in MACKINAC_WEB_DIR env var,
    or it defaults to '../../mackinac-web' relative to this script.
"""
import os
import subprocess
import sys
from pathlib import Path

HERE        = Path(__file__).parent
REPO_ROOT   = HERE.parent
MODELS_DIR  = REPO_ROOT / "mackinac" / "models"

WEB_DIR = Path(os.getenv("MACKINAC_WEB_DIR", str(HERE.parent.parent / "mackinac-web")))
SCHEMAS_DIR = WEB_DIR / "docs" / "api" / "schemas"
OPENAPI     = WEB_DIR / "docs" / "api" / "openapi.yaml"

COMMON_FLAGS = [
    "--target-python-version", "3.10",
    "--output-model-type", "pydantic_v2.BaseModel",
    "--use-annotated",
    "--strict-nullable",
]


def run(cmd: list[str]) -> None:
    print("$", " ".join(str(c) for c in cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"ERROR: command failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)


def main() -> None:
    if not SCHEMAS_DIR.exists():
        print(f"ERROR: schemas dir not found: {SCHEMAS_DIR}", file=sys.stderr)
        print("Set MACKINAC_WEB_DIR env var to the mackinac-web repo root.", file=sys.stderr)
        sys.exit(1)

    print(f"Regenerating models from {WEB_DIR}\n")

    # WS message models from JSON Schemas
    run([
        sys.executable, "-m", "datamodel_code_generator",
        "--input", str(SCHEMAS_DIR),
        "--input-file-type", "jsonschema",
        "--output", str(MODELS_DIR / "messages.py"),
        *COMMON_FLAGS,
    ])
    print(f"  -> {MODELS_DIR / 'messages.py'}")

    # REST models from OpenAPI
    if OPENAPI.exists():
        run([
            sys.executable, "-m", "datamodel_code_generator",
            "--input", str(OPENAPI),
            "--input-file-type", "openapi",
            "--output", str(MODELS_DIR / "rest.py"),
            *COMMON_FLAGS,
        ])
        print(f"  -> {MODELS_DIR / 'rest.py'}")
    else:
        print(f"WARNING: openapi.yaml not found at {OPENAPI}, skipping REST models")

    print("\nDone.  Review the generated files and update models/__init__.py if new")
    print("message types were added to the FeedMessage union.")


if __name__ == "__main__":
    main()
