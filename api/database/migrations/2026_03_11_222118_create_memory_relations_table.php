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
        Schema::create('memory_relations', function (Blueprint $table) {
            $table->id();
            $table->foreignUuid('source_id')->constrained('memories')->cascadeOnDelete();
            $table->foreignUuid('target_id')->constrained('memories')->cascadeOnDelete();
            $table->string('type')->default('related'); // e.g., 'parent', 'child', 'related', 'contradicts'
            $table->timestamps();

            $table->unique(['source_id', 'target_id', 'type']);
            $table->index(['target_id', 'type']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('memory_relations');
    }
};
