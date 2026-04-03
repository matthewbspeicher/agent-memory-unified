<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('positions', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('agent_id')->constrained()->cascadeOnDelete();
            $table->string('ticker', 64);
            $table->boolean('paper')->default(true);
            $table->decimal('quantity', 24, 8)->default(0);
            $table->decimal('avg_entry_price', 24, 8)->default(0);
            $table->timestamps();

            $table->unique(['agent_id', 'ticker', 'paper']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('positions');
    }
};
