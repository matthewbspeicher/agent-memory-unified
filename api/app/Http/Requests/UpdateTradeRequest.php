<?php

namespace App\Http\Requests;

use App\Models\Trade;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class UpdateTradeRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        $agent = $this->attributes->get('agent');
        
        return [
            'strategy' => ['nullable', 'string', 'max:255'],
            'confidence' => ['nullable', 'numeric', 'between:0,1'],
            'metadata' => ['nullable', 'array'],
            'tags' => ['nullable', 'array', 'max:20'],
            'tags.*' => ['string', 'max:50'],
            'decision_memory_id' => [
                'nullable', 'uuid',
                Rule::exists('memories', 'id')->where('agent_id', $agent->id),
            ],
            'outcome_memory_id' => [
                'nullable', 'uuid',
                Rule::exists('memories', 'id')->where('agent_id', $agent->id),
            ],
            'status' => ['nullable', Rule::in(['cancelled'])],
        ];
    }
}
