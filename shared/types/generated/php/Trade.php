<?php

namespace AgentMemory\SharedTypes;

/**
 * Trading execution record
 * Auto-generated from JSON Schema - do not edit manually
 */
class Trade
{
    public string $id;
    public string $agent_id;
    public string $ticker;
    public string $direction;
    public float $entry_price;
    public float $quantity;
    public string $entry_at;
    public ?string $exit_at;
    public ?float $exit_price;
    public string $status;
    public ?float $pnl;
    public ?float $pnl_percent;
    public ?string $strategy;
    public ?bool $paper;
    public ?string $decision_memory_id;
    public ?string $outcome_memory_id;
    public ?array $metadata;

    public function __construct(array $data)
    {
        $this->id = $data['id'] ?? null;
        $this->agent_id = $data['agent_id'] ?? null;
        $this->ticker = $data['ticker'] ?? null;
        $this->direction = $data['direction'] ?? null;
        $this->entry_price = $data['entry_price'] ?? null;
        $this->quantity = $data['quantity'] ?? null;
        $this->entry_at = $data['entry_at'] ?? null;
        $this->exit_at = $data['exit_at'] ?? null;
        $this->exit_price = $data['exit_price'] ?? null;
        $this->status = $data['status'] ?? null;
        $this->pnl = $data['pnl'] ?? null;
        $this->pnl_percent = $data['pnl_percent'] ?? null;
        $this->strategy = $data['strategy'] ?? null;
        $this->paper = $data['paper'] ?? null;
        $this->decision_memory_id = $data['decision_memory_id'] ?? null;
        $this->outcome_memory_id = $data['outcome_memory_id'] ?? null;
        $this->metadata = $data['metadata'] ?? null;
    }

    public static function validationRules(): array
    {
        return [
            'id' => ['required', 'string'],
            'agent_id' => ['required', 'string'],
            'ticker' => ['required', 'string', 'max:64'],
            'direction' => ['required', 'string', 'in:long,short'],
            'entry_price' => ['required'],
            'quantity' => ['required'],
            'entry_at' => ['required', 'string'],
            'exit_at' => ['string'],
            'exit_price' => [],
            'status' => ['required', 'string', 'in:open,closed,cancelled'],
            'pnl' => [],
            'pnl_percent' => [],
            'strategy' => ['string'],
            'paper' => [],
            'decision_memory_id' => ['string'],
            'outcome_memory_id' => ['string'],
            'metadata' => [],
        ];
    }
}
