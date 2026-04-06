<?php

namespace App\Http\Requests;

use App\Models\Memory;
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
            'agent_id' => ['sometimes', 'uuid'],
            'key' => ['nullable', 'string', 'max:255'],
            'value' => ['required', 'string', 'max:10000'],
            'type' => ['sometimes', 'string', Rule::in(Memory::TYPES)],
            'category' => ['nullable', 'string', 'max:100'],
            'visibility' => ['nullable', 'in:private,shared,public,workspace'],
            'workspace_id' => ['nullable', 'required_if:visibility,workspace', 'uuid', 'exists:workspaces,id'],
            'metadata' => ['nullable', 'array'],
            'importance' => ['nullable', 'integer', 'min:1', 'max:10'],
            'confidence' => ['nullable', 'numeric', 'min:0', 'max:1'],
            'expires_at' => ['nullable', 'date', 'after:now', 'prohibits:ttl'],
            'ttl' => ['nullable', 'string', 'regex:/^\d+[hmd]$/', 'prohibits:expires_at'],
            'tags' => ['nullable', 'array'],
            'tags.*' => ['string', 'max:50'],
        ];
    }
}
