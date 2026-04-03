<?php
// scripts/generate-php-types.php

$schemasDir = __DIR__ . '/../shared/types/schemas';
$outputDir = __DIR__ . '/../shared/types/generated/php';

if (!is_dir($outputDir)) {
    mkdir($outputDir, 0755, true);
}

$schemas = glob($schemasDir . '/*.schema.json');

foreach ($schemas as $schemaPath) {
    $schema = json_decode(file_get_contents($schemaPath), true);
    $className = ucfirst(str_replace('.schema.json', '', basename($schemaPath)));

    $phpCode = generatePHPClass($className, $schema);

    file_put_contents($outputDir . '/' . $className . '.php', $phpCode);
    echo "Generated $className.php\n";
}

function generatePHPClass(string $className, array $schema): string
{
    $properties = $schema['properties'] ?? [];
    $required = $schema['required'] ?? [];

    $code = "<?php\n\n";
    $code .= "namespace AgentMemory\\SharedTypes;\n\n";
    $code .= "/**\n";
    $code .= " * " . ($schema['description'] ?? $className) . "\n";
    $code .= " * Auto-generated from JSON Schema - do not edit manually\n";
    $code .= " */\n";
    $code .= "class $className\n";
    $code .= "{\n";

    // Properties
    foreach ($properties as $name => $prop) {
        $phpType = mapJSONTypeToPHP($prop);
        $nullable = !in_array($name, $required) ? '?' : '';
        $code .= "    public {$nullable}{$phpType} \${$name};\n";
    }

    $code .= "\n";

    // Constructor
    $code .= "    public function __construct(array \$data)\n";
    $code .= "    {\n";
    foreach ($properties as $name => $prop) {
        $code .= "        \$this->{$name} = \$data['{$name}'] ?? null;\n";
    }
    $code .= "    }\n\n";

    // Validation rules
    $code .= "    public static function validationRules(): array\n";
    $code .= "    {\n";
    $code .= "        return [\n";
    foreach ($properties as $name => $prop) {
        $rules = [];
        if (in_array($name, $required)) {
            $rules[] = "'required'";
        }
        if ($prop['type'] === 'string') {
            $rules[] = "'string'";
            if (isset($prop['maxLength'])) {
                $rules[] = "'max:{$prop['maxLength']}'";
            }
        }
        if ($prop['type'] === 'integer') {
            $rules[] = "'integer'";
        }
        if (isset($prop['enum'])) {
            $values = implode(',', $prop['enum']);
            $rules[] = "'in:{$values}'";
        }
        $rulesStr = implode(', ', $rules);
        $code .= "            '{$name}' => [{$rulesStr}],\n";
    }
    $code .= "        ];\n";
    $code .= "    }\n";

    $code .= "}\n";

    return $code;
}

function mapJSONTypeToPHP(array $prop): string
{
    return match($prop['type']) {
        'string' => 'string',
        'integer' => 'int',
        'number' => 'float',
        'boolean' => 'bool',
        'array' => 'array',
        'object' => 'array',
        default => 'mixed'
    };
}
