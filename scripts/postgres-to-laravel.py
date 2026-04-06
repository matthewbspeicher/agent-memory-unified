#!/usr/bin/env python3
"""
Generate Laravel migration from trading/storage/migrations.py (Postgres DDL).

Reads the _STATEMENTS list, converts each CREATE TABLE to Laravel Blueprint syntax.
"""
import re
import sys

def postgres_to_blueprint(ddl: str) -> str:
    """Convert Postgres CREATE TABLE to Laravel Blueprint."""

    # Parse table name
    match = re.search(r'CREATE TABLE[^(]*\s+(\w+)\s*\(', ddl, re.IGNORECASE)
    if not match:
        return ""

    table_name = match.group(1)
    result = f"        Schema::create('{table_name}', function (Blueprint $table) {{\n"

    # Extract column definitions
    columns_match = re.search(r'\((.*)\)', ddl, re.DOTALL)
    if not columns_match:
        return result + "        });\n"

    columns_block = columns_match.group(1)

    for line in columns_block.split(','):
        line = line.strip()
        if not line or line.startswith('--') or 'REFERENCES' in line:
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        col_name = parts[0]
        col_type = parts[1]

        # Handle SERIAL PRIMARY KEY
        if col_type == 'SERIAL' and 'PRIMARY' in line:
            result += f"            $table->id('{col_name}');\n"
            continue

        # Map Postgres types to Laravel
        if col_type == 'TEXT':
            chain = f"$table->text('{col_name}')"
        elif col_type == 'INTEGER':
            chain = f"$table->integer('{col_name}')"
        elif col_type in ('DOUBLE', 'PRECISION'):
            if col_type == 'DOUBLE' and parts[2] == 'PRECISION':
                chain = f"$table->double('{col_name}')"
            else:
                chain = f"$table->double('{col_name}')"
        elif col_type == 'BOOLEAN':
            chain = f"$table->boolean('{col_name}')"
        elif col_type == 'JSONB':
            chain = f"$table->jsonb('{col_name}')"
        else:
            # Fallback: use text for unknown types
            chain = f"$table->text('{col_name}')"

        # Handle NOT NULL
        if 'NOT NULL' not in line:
            chain += "->nullable()"

        # Handle DEFAULT
        if 'DEFAULT' in line:
            # Extract default value (simplified)
            default_match = re.search(r"DEFAULT\s+([^\s,)]+)", line)
            if default_match:
                default_val = default_match.group(1)
                if default_val in ('NOW()', 'FALSE', 'TRUE', '0'):
                    if default_val == 'NOW()':
                        chain += "->useCurrent()"
                    elif default_val == 'FALSE':
                        chain += "->default(false)"
                    elif default_val == 'TRUE':
                        chain += "->default(true)"
                    elif default_val == '0':
                        chain += "->default(0)"
                elif default_val.startswith("'"):
                    chain += f"->default({default_val})"

        result += f"            {chain};\n"

    result += "        });\n"
    return result

def main():
    # Read migrations.py
    with open('trading/storage/migrations.py', 'r') as f:
        content = f.read()

    # Extract _STATEMENTS list
    statements_match = re.search(r'_STATEMENTS:\s*list\[str\]\s*=\s*\[(.*?)\]', content, re.DOTALL)
    if not statements_match:
        print("ERROR: Could not find _STATEMENTS list", file=sys.stderr)
        sys.exit(1)

    statements_block = statements_match.group(1)

    # Split by triple-quoted strings
    tables = re.findall(r'"""(.*?)"""', statements_block, re.DOTALL)

    # Generate migration
    print("<?php\n")
    print("use Illuminate\\Database\\Migrations\\Migration;")
    print("use Illuminate\\Database\\Schema\\Blueprint;")
    print("use Illuminate\\Support\\Facades\\Schema;\n")
    print("return new class extends Migration")
    print("{")
    print("    public function up(): void")
    print("    {")

    for table_ddl in tables:
        if 'CREATE TABLE' in table_ddl:
            blueprint = postgres_to_blueprint(table_ddl)
            if blueprint:
                print(blueprint)

    # Generate indexes (simplified - just show CREATE INDEX statements as comments)
    print("\n        // Indexes")
    for stmt in re.findall(r'"(CREATE INDEX[^"]+)"', statements_block):
        print(f"        // {stmt}")

    print("    }\n")
    print("    public function down(): void")
    print("    {")
    print("        // Drop tables in reverse order")
    for table_ddl in reversed(tables):
        match = re.search(r'CREATE TABLE[^(]*\s+(\w+)', table_ddl)
        if match:
            print(f"        Schema::dropIfExists('{match.group(1)}');")
    print("    }")
    print("};")

if __name__ == '__main__':
    main()
