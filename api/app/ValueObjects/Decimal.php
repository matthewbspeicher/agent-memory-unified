<?php

namespace App\ValueObjects;

use InvalidArgumentException;

class Decimal
{
    private string $value;
    private int $scale;

    public function __construct(string|int|float|Decimal $value, int $scale = 8)
    {
        $this->scale = $scale;
        
        if ($value instanceof Decimal) {
            $this->value = bcadd($value->toString(), '0', $this->scale);
        } elseif (is_float($value)) {
            $this->value = sprintf('%.*F', $scale, $value);
        } else {
            $this->value = bcadd((string) $value, '0', $this->scale);
        }
    }

    public static function from(string|int|float|Decimal $value, int $scale = 8): self
    {
        return new self($value, $scale);
    }

    public function add(string|int|float|Decimal $other): self
    {
        $otherValue = $other instanceof Decimal ? $other->toString() : (new self($other, $this->scale))->toString();
        return new self(bcadd($this->value, $otherValue, $this->scale), $this->scale);
    }

    public function sub(string|int|float|Decimal $other): self
    {
        $otherValue = $other instanceof Decimal ? $other->toString() : (new self($other, $this->scale))->toString();
        return new self(bcsub($this->value, $otherValue, $this->scale), $this->scale);
    }

    public function mul(string|int|float|Decimal $other): self
    {
        $otherValue = $other instanceof Decimal ? $other->toString() : (new self($other, $this->scale))->toString();
        return new self(bcmul($this->value, $otherValue, $this->scale), $this->scale);
    }

    public function div(string|int|float|Decimal $other): self
    {
        $otherValue = $other instanceof Decimal ? $other->toString() : (new self($other, $this->scale))->toString();
        
        if (bccomp($otherValue, '0', $this->scale) === 0) {
            throw new InvalidArgumentException("Division by zero");
        }
        
        return new self(bcdiv($this->value, $otherValue, $this->scale), $this->scale);
    }

    public function comp(string|int|float|Decimal $other): int
    {
        $otherValue = $other instanceof Decimal ? $other->toString() : (new self($other, $this->scale))->toString();
        return bccomp($this->value, $otherValue, $this->scale);
    }

    public function isGreaterThan(string|int|float|Decimal $other): bool
    {
        return $this->comp($other) > 0;
    }

    public function isLessThan(string|int|float|Decimal $other): bool
    {
        return $this->comp($other) < 0;
    }

    public function isEqualTo(string|int|float|Decimal $other): bool
    {
        return $this->comp($other) === 0;
    }
    
    public function isGreaterThanOrEqualTo(string|int|float|Decimal $other): bool
    {
        return $this->comp($other) >= 0;
    }

    public function isLessThanOrEqualTo(string|int|float|Decimal $other): bool
    {
        return $this->comp($other) <= 0;
    }
    
    public function abs(): self
    {
        if ($this->isLessThan('0')) {
            return $this->mul('-1');
        }
        return new self($this->value, $this->scale);
    }

    public function toString(): string
    {
        return $this->value;
    }

    public function __toString(): string
    {
        return $this->value;
    }
}
