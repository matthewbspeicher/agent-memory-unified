<?php

namespace Tests\Unit\Models;

use App\Models\Workspace;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Str;
use Tests\TestCase;

class WorkspaceTest extends TestCase
{
    use RefreshDatabase;

    public function test_it_can_create_a_workspace(): void
    {
        $workspace = Workspace::create([
            'name' => 'Project Alpha',
            'description' => 'A test workspace for project alpha.',
            'slug' => Str::slug('Project Alpha'),
        ]);

        $this->assertDatabaseHas('workspaces', [
            'name' => 'Project Alpha',
            'slug' => 'project-alpha',
        ]);

        $this->assertInstanceOf(Workspace::class, $workspace);
    }
}
