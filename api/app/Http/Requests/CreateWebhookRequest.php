<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class CreateWebhookRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return [
            'url' => ['required', 'url', 'starts_with:https://'],
            'events' => ['required', 'array', 'min:1'],
            'events.*' => ['string', 'in:memory.shared,memory.semantic_match,trade.opened,trade.closed,position.changed,alert.triggered'],
            'semantic_query' => ['nullable', 'string', 'max:1000'],
        ];
    }
}
