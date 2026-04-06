<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class CreateTaskRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return [
            'workspace_id' => ['required', 'uuid', 'exists:workspaces,id'],
            'title' => ['required', 'string', 'max:255'],
            'description' => ['sometimes', 'string', 'max:10000'],
            'assigned_to' => ['sometimes', 'uuid', 'exists:agents,id'],
            'priority' => ['sometimes', Rule::in(['low', 'medium', 'high', 'critical'])],
            'due_at' => ['sometimes', 'date'],
            'agent_id' => ['sometimes', 'uuid'],
        ];
    }
}
