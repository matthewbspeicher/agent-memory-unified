<?php

namespace Tests\Unit;

use App\Models\Trade;
use App\Services\TradeProcessor;
use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\DataProvider;

class TradeProcessorTest extends TestCase
{
    #[DataProvider('provideMathVectors')]
    public function test_compute_child_pnl_matches_shared_vectors(array $vector)
    {
        $service = new TradeProcessor();

        // Create mock/dummy parent trade
        $parent = new Trade();
        $parent->direction = $vector['parent_direction'];
        $parent->entry_price = $vector['parent_entry'];
        $parent->quantity = $vector['parent_quantity'];
        $parent->fees = $vector['parent_fees'];

        // Create mock/dummy child trade
        $child = new Trade();
        $child->entry_price = $vector['child_entry'];
        $child->quantity = $vector['child_quantity'];
        $child->fees = $vector['child_fees'];

        $result = $service->computeChildPnl($child, $parent);

        // Assert net pnl matches exactly up to 8 decimal places
        // The service might return fewer decimals if it strips trailing zeros,
        // so we format both to 8 decimals for strict comparison.
        $this->assertSame(
            number_format((float)$vector['expected_net_pnl'], 8, '.', ''),
            number_format((float)$result['pnl'], 8, '.', ''),
            "Net PnL mismatch for scenario: {$vector['description']}"
        );

        // Assert pnl_percent matches exactly up to 4 decimal places
        $this->assertSame(
            number_format((float)$vector['expected_pnl_percent'], 4, '.', ''),
            number_format((float)$result['pnl_percent'], 4, '.', ''),
            "PnL Percent mismatch for scenario: {$vector['description']}"
        );
    }

    public static function provideMathVectors(): array
    {
        $path = __DIR__ . '/../../../shared/tests/math_vectors.json';
        if (!file_exists($path)) {
            return [];
        }

        $json = file_get_contents($path);
        $vectors = json_decode($json, true);

        $data = [];
        foreach ($vectors as $vector) {
            $data[$vector['description']] = [$vector];
        }

        return $data;
    }
}
