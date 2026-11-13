"""Sanitized observations from existing, best-effort storage initialization.

An issue records an attempted step, not a final readiness verdict: a later
legacy fixup may repair an earlier failure. No SQL, exception message or
connection configuration is retained here.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InitializationIssue:
    step: str
    error_type: str


@dataclass
class InitializationReport:
    issues: list[InitializationIssue] = field(default_factory=list)

    def record(self, step: str, error: BaseException) -> None:
        self.issues.append(
            InitializationIssue(step=step, error_type=type(error).__name__)
        )
