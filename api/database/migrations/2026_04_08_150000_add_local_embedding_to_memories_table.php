<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        // Add local_embedding column for all-MiniLM-L6-v2 (384 dimensions)
        DB::statement('ALTER TABLE memories ADD COLUMN local_embedding vector(384)');

        // IVFFlat index for approximate nearest-neighbor search
        DB::statement('CREATE INDEX memories_local_embedding_idx ON memories USING ivfflat (local_embedding vector_cosine_ops) WITH (lists = 50)');
    }

    public function down(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement('DROP INDEX IF EXISTS memories_local_embedding_idx');
        DB::statement('ALTER TABLE memories DROP COLUMN IF EXISTS local_embedding');
    }
};
