<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class StoreMemoryRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true; // Auth handled by middleware
    }

    public function rules(): array
    {
        return [
            'value' => ['required', 'string', 'min:1', 'max:100000'],
            'type' => ['sometimes', Rule::in(['note', 'lesson', 'preference', 'fact', 'procedure'])],
            'visibility' => ['sometimes', Rule::in(['private', 'public'])],
            'tags' => ['sometimes', 'array'],
            'tags.*' => ['string'],
            'metadata' => ['sometimes', 'array'],
            'ttl' => ['sometimes', 'string'],
            'workspace_id' => ['sometimes', 'uuid'],
            'agent_id' => ['sometimes', 'uuid'],
        ];
    }
}
