<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('memory_shares', function (Blueprint $table) {
            $table->id();
            $table->foreignUuid('memory_id')->constrained()->cascadeOnDelete();
            $table->foreignUuid('agent_id')->constrained()->cascadeOnDelete(); // the recipient
            $table->timestamp('created_at');

            $table->unique(['memory_id', 'agent_id']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('memory_shares');
    }
};
