<?php

namespace App\Rules;

use App\Models\Agent;
use Closure;
use Illuminate\Contracts\Validation\ValidationRule;

class BelongsToWorkspace implements ValidationRule
{
    public function __construct(
        private readonly Agent $agent,
    ) {}

    public function validate(string $attribute, mixed $value, Closure $fail): void
    {
        if (! $this->agent->workspaces()->where('workspaces.id', $value)->exists()) {
            $fail('The selected workspace is not accessible by this agent.');
        }
    }
}
