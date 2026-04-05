#!/bin/bash
set -e

# Type generation script for shared types
# Reads JSON Schemas from schemas/, outputs to generated/
# Also copies Python types into shared_types package for clean imports

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MONOREPO_ROOT="$(cd "$ROOT_DIR/../.." && pwd)"

SCHEMAS_DIR="$ROOT_DIR/schemas"
OUT_PY="$ROOT_DIR/generated/python"
OUT_TS="$ROOT_DIR/generated/typescript"
OUT_PHP="$ROOT_DIR/generated/php"
PY_PKG="$MONOREPO_ROOT/shared/types-py/shared_types"

echo "🔧 Generating types from JSON Schemas..."

# Generate Python (Pydantic v2)
echo "→ Python (Pydantic)..."
for schema in "$SCHEMAS_DIR"/*.schema.json; do
  name=$(basename "$schema" .schema.json)
  datamodel-codegen \
    --input "$schema" \
    --output "$OUT_PY/${name}.py" \
    --output-model-type pydantic_v2.BaseModel \
    --use-default \
    --use-standard-collections
done

# Copy generated Python files into shared_types package
# This avoids fragile sys.path hacks and bare imports
if [ -d "$PY_PKG" ]; then
  echo "→ Copying Python types into shared_types package..."
  cp "$OUT_PY"/*.py "$PY_PKG/"
fi

# Generate TypeScript
echo "→ TypeScript..."
for schema in "$SCHEMAS_DIR"/*.schema.json; do
  name=$(basename "$schema" .schema.json)
  quicktype "$schema" \
    --lang typescript \
    --src-lang schema \
    --out "$OUT_TS/${name}.ts" \
    --just-types
done

# Generate PHP (placeholder for now - no great schema → PHP generator)
echo "→ PHP (manual for now)..."
echo "// TODO: Implement PHP type generation" > "$OUT_PHP/README.md"
echo "// Consider: jane-php/json-schema or custom Jinja2 templates" >> "$OUT_PHP/README.md"

echo "✅ Types generated successfully"
echo "   Python: $OUT_PY"
echo "   TypeScript: $OUT_TS"
echo "   PHP: $OUT_PHP (manual)"
