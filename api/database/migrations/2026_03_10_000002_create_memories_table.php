<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        // Enable pgvector extension (PostgreSQL only)
        if (DB::getDriverName() === 'pgsql') {
            DB::statement('CREATE EXTENSION IF NOT EXISTS vector');
        }

        Schema::create('memories', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('agent_id')->constrained()->cascadeOnDelete();
            $table->string('key')->nullable();
            $table->text('value');
            $table->json('metadata')->default('{}');
            $table->enum('visibility', ['private', 'shared', 'public'])->default('private');
            $table->timestamp('expires_at')->nullable();
            $table->timestamps();

            // Composite index for fast per-agent key lookup
            $table->unique(['agent_id', 'key']);
            $table->index(['agent_id', 'visibility']);
            $table->index('visibility'); // for commons search

            // Add vector column for SQLite (as text or blob) if needed, 
            // but for now we'll just skip it as we don't have sqlite-vector extension here.
            if (DB::getDriverName() !== 'pgsql') {
                $table->text('embedding')->nullable();
            }
        });

        if (DB::getDriverName() === 'pgsql') {
            // Add the vector column separately (pgvector syntax)
            // 1536 dimensions = OpenAI text-embedding-3-small
            DB::statement('ALTER TABLE memories ADD COLUMN embedding vector(1536)');

            // IVFFlat index for approximate nearest-neighbor search
            // Lists = sqrt(expected_row_count), tune later
            DB::statement('CREATE INDEX memories_embedding_idx ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)');
        }
    }

    public function down(): void
    {
        Schema::dropIfExists('memories');
    }
};
