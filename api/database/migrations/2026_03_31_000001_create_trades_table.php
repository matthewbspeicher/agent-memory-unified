<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('trades', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('agent_id')->constrained()->cascadeOnDelete();
            $table->uuid('parent_trade_id')->nullable();
            $table->string('ticker', 64);
            $table->string('direction'); // long, short
            $table->decimal('entry_price', 24, 8);
            $table->decimal('exit_price', 24, 8)->nullable();
            $table->decimal('quantity', 24, 8);
            $table->decimal('fees', 24, 8)->default(0);
            $table->timestamp('entry_at');
            $table->timestamp('exit_at')->nullable();
            $table->string('status')->default('open'); // open, closed, cancelled
            $table->decimal('pnl', 24, 8)->nullable();
            $table->decimal('pnl_percent', 8, 4)->nullable();
            $table->string('strategy')->nullable();
            $table->float('confidence')->nullable();
            $table->boolean('paper')->default(true);
            $table->foreignUuid('decision_memory_id')->nullable()->constrained('memories')->nullOnDelete();
            $table->foreignUuid('outcome_memory_id')->nullable()->constrained('memories')->nullOnDelete();
            $table->jsonb('metadata')->nullable();
            $table->softDeletes();
            $table->timestamps();

            $table->index(['agent_id', 'status']);
            $table->index(['agent_id', 'ticker', 'paper']);
            $table->index(['agent_id', 'paper', 'created_at']);
            $table->index('parent_trade_id');
            $table->index('strategy');
        });

        Schema::table('trades', function (Blueprint $table) {
            $table->foreign('parent_trade_id')->references('id')->on('trades')->nullOnDelete();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('trades');
    }
};
