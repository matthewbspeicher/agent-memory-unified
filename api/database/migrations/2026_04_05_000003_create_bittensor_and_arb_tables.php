<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        // Arbitrage Spread Observations
        Schema::create('arb_spread_observations', function (Blueprint $table) {
            $table->id();
            $table->string('kalshi_ticker');
            $table->string('poly_ticker');
            $table->decimal('match_score', 5, 4);
            $table->integer('kalshi_cents');
            $table->integer('poly_cents');
            $table->integer('gap_cents');
            $table->decimal('kalshi_volume', 20, 8)->default(0);
            $table->decimal('poly_volume', 20, 8)->default(0);
            $table->boolean('is_claimed')->default(false);
            $table->timestamp('claimed_at')->nullable();
            $table->string('claimed_by')->nullable();
            $table->timestamps();

            $table->index(['kalshi_ticker', 'poly_ticker', 'created_at']);
            $table->index(['gap_cents', 'created_at']);
        });

        // Arbitrage Trades
        Schema::create('arb_trades', function (Blueprint $table) {
            $table->string('id')->primary();
            $table->string('symbol_a');
            $table->string('symbol_b');
            $table->integer('expected_profit_bps');
            $table->string('sequencing');
            $table->string('state')->index();
            $table->text('error_message')->nullable();
            $table->timestamps();
        });

        // Arbitrage Legs
        Schema::create('arb_legs', function (Blueprint $table) {
            $table->string('trade_id');
            $table->string('leg_name');
            $table->string('broker_id');
            $table->jsonb('order_data');
            $table->decimal('fill_price', 20, 8)->nullable();
            $table->decimal('fill_quantity', 20, 8);
            $table->string('status');
            $table->string('external_order_id')->nullable();
            $table->timestamps();

            $table->primary(['trade_id', 'leg_name']);
            $table->foreign('trade_id')->references('id')->on('arb_trades')->onDelete('cascade');
            $table->index('trade_id');
        });

        // Bittensor Raw Forecasts
        Schema::create('bittensor_raw_forecasts', function (Blueprint $table) {
            $table->id();
            $table->string('window_id');
            $table->string('request_uuid');
            $table->timestamp('collected_at');
            $table->string('stream_id');
            $table->integer('topic_id');
            $table->integer('schema_id');
            $table->string('symbol');
            $table->string('timeframe');
            $table->string('feature_ids');
            $table->integer('prediction_size');
            $table->integer('miner_uid')->nullable();
            $table->string('miner_hotkey');
            $table->text('predictions');
            $table->string('hashed_predictions')->nullable();
            $table->boolean('hash_verified')->default(false);
            $table->decimal('incentive_score', 8, 6)->nullable();
            $table->decimal('vtrust', 8, 6)->nullable();
            $table->decimal('stake_tao', 20, 8)->nullable();
            $table->bigInteger('metagraph_block')->nullable();
            $table->timestamps();

            $table->index('window_id');
            $table->index(['symbol', 'timeframe', 'collected_at']);
            $table->index(['miner_hotkey', 'collected_at']);
            $table->unique(['window_id', 'miner_hotkey', 'request_uuid'], 'bt_raw_unique');
        });

        // Bittensor Derived Views
        Schema::create('bittensor_derived_views', function (Blueprint $table) {
            $table->string('window_id')->primary();
            $table->string('symbol');
            $table->string('timeframe');
            $table->timestamp('timestamp');
            $table->integer('responder_count');
            $table->integer('bullish_count');
            $table->integer('bearish_count');
            $table->integer('flat_count');
            $table->decimal('weighted_direction', 8, 4);
            $table->decimal('weighted_expected_return', 8, 4);
            $table->decimal('agreement_ratio', 5, 4);
            $table->decimal('equal_weight_direction', 8, 4);
            $table->decimal('equal_weight_expected_return', 8, 4);
            $table->boolean('is_low_confidence')->default(false);
            $table->string('derivation_version');
            $table->string('evaluation_status')->default('pending');
            $table->timestamps();

            $table->index(['symbol', 'timeframe', 'timestamp']);
        });

        // Bittensor Realized Windows
        Schema::create('bittensor_realized_windows', function (Blueprint $table) {
            $table->string('window_id')->primary();
            $table->string('symbol');
            $table->string('timeframe');
            $table->text('realized_path');
            $table->decimal('realized_return', 8, 4);
            $table->integer('bars_used');
            $table->string('source');
            $table->timestamp('captured_at');
            $table->timestamps();

            $table->index(['symbol', 'timeframe', 'captured_at']);
        });

        // Bittensor Accuracy Records
        Schema::create('bittensor_accuracy_records', function (Blueprint $table) {
            $table->id();
            $table->string('window_id');
            $table->string('miner_hotkey');
            $table->string('symbol');
            $table->string('timeframe');
            $table->boolean('direction_correct');
            $table->decimal('predicted_return', 8, 4);
            $table->decimal('actual_return', 8, 4);
            $table->decimal('magnitude_error', 8, 4);
            $table->decimal('path_correlation', 8, 6)->nullable();
            $table->integer('outcome_bars');
            $table->string('scoring_version');
            $table->timestamp('evaluated_at');
            $table->timestamps();

            $table->unique(['window_id', 'miner_hotkey']);
            $table->index(['miner_hotkey', 'evaluated_at']);
            $table->index(['window_id', 'miner_hotkey']);
            $table->index(['symbol', 'timeframe', 'evaluated_at']);
        });

        // Bittensor Miner Rankings
        Schema::create('bittensor_miner_rankings', function (Blueprint $table) {
            $table->string('miner_hotkey')->primary();
            $table->integer('windows_evaluated');
            $table->decimal('direction_accuracy', 5, 4);
            $table->decimal('mean_magnitude_error', 8, 4);
            $table->decimal('mean_path_correlation', 8, 6)->nullable();
            $table->decimal('internal_score', 8, 4);
            $table->decimal('latest_incentive_score', 8, 6)->nullable();
            $table->decimal('hybrid_score', 8, 4);
            $table->decimal('alpha_used', 5, 4);
            $table->timestamps();

            $table->index('hybrid_score');
            $table->index('internal_score');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('bittensor_miner_rankings');
        Schema::dropIfExists('bittensor_accuracy_records');
        Schema::dropIfExists('bittensor_realized_windows');
        Schema::dropIfExists('bittensor_derived_views');
        Schema::dropIfExists('bittensor_raw_forecasts');
        Schema::dropIfExists('arb_legs');
        Schema::dropIfExists('arb_trades');
        Schema::dropIfExists('arb_spread_observations');
    }
};
