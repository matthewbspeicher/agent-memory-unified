#!/bin/bash
set -e

echo "🔄 Generating types from JSON Schema..."

# Python: Generate Pydantic models
echo "  → Python (Pydantic)..."
datamodel-codegen \
  --input shared/types/schemas/ \
  --output shared/types/generated/python/ \
  --output-model-type pydantic_v2.BaseModel \
  --use-standard-collections \
  --field-constraints \
  --target-python-version 3.12 \
  --disable-timestamp

# TypeScript: Generate types
echo "  → TypeScript..."
npx quicktype \
  -s schema shared/types/schemas/*.json \
  --out shared/types/generated/typescript/index.ts \
  --lang typescript \
  --just-types

# PHP: Generate DTOs
echo "  → PHP (DTOs)..."
php scripts/generate-php-types.php

echo "✅ Types synchronized"
