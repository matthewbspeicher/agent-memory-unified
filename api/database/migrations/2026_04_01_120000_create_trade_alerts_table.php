<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('trade_alerts', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('agent_id')->constrained()->cascadeOnDelete();
            $table->string('ticker', 64)->nullable();
            $table->string('condition');
            $table->decimal('threshold', 24, 8)->nullable();
            $table->string('delivery', 20)->default('webhook');
            $table->boolean('is_active')->default(true);
            $table->integer('trigger_count')->default(0);
            $table->timestamp('last_triggered_at')->nullable();
            $table->timestamps();

            $table->index(['agent_id', 'is_active']);
            $table->index(['ticker', 'condition', 'is_active']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('trade_alerts');
    }
};
