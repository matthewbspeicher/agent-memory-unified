<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        if (DB::getDriverName() === 'pgsql') {
            // Add the column
            DB::statement('ALTER TABLE memories ADD COLUMN IF NOT EXISTS search_vector tsvector');

            // Update existing rows
            DB::statement("UPDATE memories SET search_vector = to_tsvector('english', coalesce(value, ''))");

            // Create an index
            DB::statement('CREATE INDEX IF NOT EXISTS memories_search_vector_idx ON memories USING GIN(search_vector)');

            // Add a trigger to update the vector on insert/update
            DB::statement("
                CREATE OR REPLACE FUNCTION memories_search_vector_update() RETURNS trigger AS $$
                BEGIN
                  NEW.search_vector := to_tsvector('english', coalesce(NEW.value, ''));
                  RETURN NEW;
                END
                $$ LANGUAGE plpgsql;
            ");

            DB::statement('
                CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE
                ON memories FOR EACH ROW EXECUTE FUNCTION memories_search_vector_update();
            ');
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        if (DB::getDriverName() === 'pgsql') {
            DB::statement('DROP TRIGGER IF EXISTS tsvectorupdate ON memories');
            DB::statement('DROP FUNCTION IF EXISTS memories_search_vector_update()');
            DB::statement('DROP INDEX IF EXISTS memories_search_vector_idx');
            DB::statement('ALTER TABLE memories DROP COLUMN IF EXISTS search_vector');
        }
    }
};
