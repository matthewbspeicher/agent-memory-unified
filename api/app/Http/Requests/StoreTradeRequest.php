<?php

namespace App\Http\Requests;

use App\Models\Trade;
use Closure;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class StoreTradeRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        $agent = $this->attributes->get('agent');

        return [
            'ticker' => ['required', 'string', 'max:64'],
            'direction' => ['required', Rule::in(Trade::DIRECTIONS)],
            'entry_price' => ['required', 'numeric', 'gt:0'],
            'quantity' => ['required', 'numeric', 'gt:0'],
            'entry_at' => ['required', 'date'],
            'fees' => ['nullable', 'numeric', 'gte:0'],
            'strategy' => ['nullable', 'string', 'max:255'],
            'confidence' => ['nullable', 'numeric', 'between:0,1'],
            'paper' => ['boolean'],
            'parent_trade_id' => [
                'nullable',
                'uuid',
                function (string $attribute, mixed $value, Closure $fail) use ($agent) {
                    if (! $value) {
                        return;
                    }

                    $parent = Trade::where('id', $value)
                        ->where('agent_id', $agent->id)
                        ->first();

                    if (! $parent) {
                        $fail('Parent trade not found or does not belong to this agent.');
                        return;
                    }

                    if ($parent->status !== 'open') {
                        $fail('Parent trade is not open.');
                        return;
                    }

                    if ($this->input('direction') === $parent->direction) {
                        $fail('Exit direction must oppose the parent trade direction.');
                        return;
                    }

                    if ($this->input('ticker') !== $parent->ticker) {
                        $fail('Exit ticker must match parent trade ticker.');
                        return;
                    }

                    if ((bool) $this->input('paper', true) !== $parent->paper) {
                        $fail('Exit paper flag must match parent trade.');
                        return;
                    }

                    $existingChildQty = $parent->children()->sum('quantity');
                    $newQty = $this->input('quantity');
                    $remaining = bcsub($parent->quantity, (string) $existingChildQty, 8);

                    if (bccomp((string) $newQty, $remaining, 8) > 0) {
                        $fail("Exit quantity ({$newQty}) exceeds remaining parent quantity ({$remaining}).");
                    }
                },
            ],
            'decision_memory_id' => [
                'nullable', 'uuid',
                Rule::exists('memories', 'id')->where('agent_id', $agent->id),
            ],
            'outcome_memory_id' => [
                'nullable', 'uuid',
                Rule::exists('memories', 'id')->where('agent_id', $agent->id),
            ],
            'metadata' => ['nullable', 'array'],
            'tags' => ['nullable', 'array', 'max:20'],
            'tags.*' => ['string', 'max:50'],
        ];
    }
}
