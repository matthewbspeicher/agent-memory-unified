<?php

namespace App\Http\Requests;

use App\Models\Memory;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class UpdateMemoryRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return [
            'value' => ['sometimes', 'string', 'max:10000'],
            'type' => ['sometimes', 'string', Rule::in(Memory::TYPES)],
            'category' => ['sometimes', 'nullable', 'string', 'max:100'],
            'visibility' => ['sometimes', 'in:private,shared,public,workspace'],
            'workspace_id' => ['sometimes', 'nullable', 'required_if:visibility,workspace', 'uuid', 'exists:workspaces,id'],
            'metadata' => ['sometimes', 'array'],
            'importance' => ['sometimes', 'integer', 'min:1', 'max:10'],
            'confidence' => ['sometimes', 'numeric', 'min:0', 'max:1'],
            'expires_at' => ['sometimes', 'nullable', 'date', 'after:now', 'prohibits:ttl'],
            'ttl' => ['sometimes', 'nullable', 'string', 'regex:/^\d+[hmd]$/', 'prohibits:expires_at'],
            'tags' => ['sometimes', 'array', 'max:10'],
            'tags.*' => ['string', 'max:50'],
        ];
    }
}
