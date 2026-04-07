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
            'key' => ['sometimes', 'nullable', 'string', 'max:255'],
            'value' => ['required', 'string', 'min:1', 'max:100000'],
            'type' => ['sometimes', 'string', Rule::in(\App\Models\Memory::TYPES)],
            'category' => ['sometimes', 'nullable', 'string', 'max:100'],
            'visibility' => ['sometimes', Rule::in(['private', 'public', 'workspace', 'shared'])],
            'importance' => ['sometimes', 'integer', 'min:1', 'max:10'],
            'confidence' => ['sometimes', 'numeric', 'min:0', 'max:1'],
            'tags' => ['sometimes', 'array', 'max:10'],
            'tags.*' => ['string', 'max:50'],
            'metadata' => ['sometimes', 'array'],
            'expires_at' => ['sometimes', 'nullable', 'date', 'after:now', 'prohibits:ttl'],
            'ttl' => ['sometimes', 'nullable', 'string', 'regex:/^\d+[hmd]$/', 'prohibits:expires_at'],
            'workspace_id' => ['sometimes', 'uuid'],
            'agent_id' => ['sometimes', 'uuid'],
        ];
    }
}
