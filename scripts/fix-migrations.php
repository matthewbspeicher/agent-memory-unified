<?php

$filePath = '/opt/homebrew/var/www/agent-memory-unified/api/database/migrations/2026_04_13_000000_create_trading_tables.php';
$content = file_get_contents($filePath);

$redundantTables = [
    'opportunities',
    'trades',
    'risk_events',
    'performance_snapshots',
    'opportunity_snapshots',
    'whatsapp_sessions',
    'tracked_positions',
    'external_positions',
    'external_balances',
    'consensus_votes',
    'execution_quality',
    'execution_cost_events',
    'execution_cost_stats',
    'trade_analytics',
];

$lines = explode("\n", $content);
$outputLines = [];
$commentingOut = false;

foreach ($lines as $line) {
    // Start commenting out if we find Schema::create or Schema::table for a redundant table
    if (preg_match("/^(\s+)Schema::(create|table)\('([^']+)',/", $line, $matches)) {
        $tableName = $matches[3];
        if (in_array($tableName, $redundantTables)) {
            $commentingOut = true;
        }
    }
    
    // Also check for DB::statement which might refer to redundant tables
    // In this file, there is one for leaderboard_cache constraint, but leaderboard_cache is unique?
    // Wait, the error was on leaderboard_cache!
    // SQL: ALTER TABLE leaderboard_cache ADD CONSTRAINT chk_leaderboard_single_row CHECK (id = 1)
    // Is leaderboard_cache created elsewhere?
    
    if ($commentingOut) {
        $outputLines[] = "// " . $line;
    } else {
        $outputLines[] = $line;
    }
    
    // Stop commenting out at the end of the block
    if ($commentingOut && trim($line) === "});") {
        $commentingOut = false;
    }
}

$finalContent = implode("\n", $outputLines);

// Also comment out the offending DB::statement for leaderboard_cache IF it's failing
// Actually, let's see why leaderboard_cache failed. 
// Maybe the table was created but the constraint was already there?
// Or maybe the table wasn't created because of a previous error?

$finalContent = str_replace(
    "DB::statement('ALTER TABLE leaderboard_cache ADD CONSTRAINT chk_leaderboard_single_row CHECK (id = 1)');",
    "// DB::statement('ALTER TABLE leaderboard_cache ADD CONSTRAINT chk_leaderboard_single_row CHECK (id = 1)');",
    $finalContent
);

file_put_contents($filePath, $finalContent);
echo "Updated $filePath\n";
