<?php

namespace AgentMemory\SharedTypes;

/**
 * Simplified trade DTO for API responses (subset of tracked_positions table)
 * Auto-generated from JSON Schema - do not edit manually
 */
class Trade
{
    public int $id;
    public string $agent_name;
    public ?string $agent_id;
    public string $symbol;
    public string $side;
    public string $entry_price;
    public int $entry_quantity;
    public string $status;
    public string $entry_time;
    public ?mixed $exit_time;
    public ?mixed $exit_price;
    public ?mixed $pnl;
    public ?mixed $pnl_percent;
    public ?string $strategy;
    public ?bool $paper;
    public ?mixed $decision_memory_id;
    public ?mixed $outcome_memory_id;
    public ?array $metadata;

    public function __construct(array $data)
    {
        $this->id = $data['id'] ?? null;
        $this->agent_name = $data['agent_name'] ?? null;
        $this->agent_id = $data['agent_id'] ?? null;
        $this->symbol = $data['symbol'] ?? null;
        $this->side = $data['side'] ?? null;
        $this->entry_price = $data['entry_price'] ?? null;
        $this->entry_quantity = $data['entry_quantity'] ?? null;
        $this->status = $data['status'] ?? null;
        $this->entry_time = $data['entry_time'] ?? null;
        $this->exit_time = $data['exit_time'] ?? null;
        $this->exit_price = $data['exit_price'] ?? null;
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
            'id' => ['required', 'integer'],
            'agent_name' => ['required', 'string'],
            'agent_id' => ['string'],
            'symbol' => ['required', 'string', 'max:64'],
            'side' => ['required', 'string', 'in:long,short'],
            'entry_price' => ['required', 'string'],
            'entry_quantity' => ['required', 'integer'],
            'status' => ['required', 'string', 'in:open,closed,cancelled'],
            'entry_time' => ['required', 'string'],
            'exit_time' => [],
            'exit_price' => [],
            'pnl' => [],
            'pnl_percent' => [],
            'strategy' => ['string', 'max:255'],
            'paper' => [],
            'decision_memory_id' => [],
            'outcome_memory_id' => [],
            'metadata' => [],
        ];
    }
}
