from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Rule:
    name: str
    condition: str
    threshold: float | None = None
    enabled: bool = True


@dataclass
class RuleSet:
    name: str
    description: str = ""
    entry_rules: list[Rule] = field(default_factory=list)
    exit_rules: list[Rule] = field(default_factory=list)
    risk_rules: list[Rule] = field(default_factory=list)


@dataclass
class RuleResult:
    rule: Rule
    passed: bool
    actual: Any
    required: str


@dataclass
class RuleSetResult:
    rule_set: RuleSet
    results: list[RuleResult]
    all_pass: bool

    @property
    def failed_rules(self) -> list[RuleResult]:
        return [r for r in self.results if not r.passed]
