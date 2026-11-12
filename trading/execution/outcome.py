"""In-process interpretation of Order outcome evidence, without lifecycle policy.

Validation and inspection are separate: a broker receipt need not satisfy the
router's priced-fill requirements. No fact here grants permission to retry or
changes admission, reservations, dispatch, acknowledgement or recovery.
"""

from dataclasses import dataclass
from decimal import Decimal

from broker.models import OrderResult, OrderStatus


class ExecutionRejected(RuntimeError):
    """No broker mutation occurred: policy or input rejected the request."""


class ExecutionUnavailable(ExecutionRejected):
    """Admission is unavailable; outcome_unknown forbids assuming rejection."""

    def __init__(self, message, *, outcome_unknown=False):
        super().__init__(message)
        self.outcome_unknown = outcome_unknown


def _decimal(value, name, *, positive=True):
    if isinstance(value, bool):
        raise ExecutionRejected(f"Invalid {name}")
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ExecutionRejected(f"Invalid {name}") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise ExecutionRejected(f"Invalid {name}")
    return result


def validate_receipt(result, *, admitted_quantity):
    """Apply existing execution checks, preserving raw values and error order.

    The admitted quantity is the risk-adjusted quantity actually dispatched.
    A rejected amendment can leave the original order active. Price qualification
    is intentionally inspection, not an additional admission check.
    """
    if (
        isinstance(result, OrderResult)
        and result.status == OrderStatus.REJECTED
        and result.filled_quantity == 0
    ):
        return result
    if not isinstance(result, OrderResult) or not result.order_id:
        raise ExecutionUnavailable("Broker returned no authoritative order receipt")
    if result.status not in set(OrderStatus):
        raise ExecutionUnavailable("Broker returned unknown order status")
    filled = _decimal(result.filled_quantity, "receipt filled quantity", positive=False)
    if (
        filled < 0
        or filled > admitted_quantity
        or (result.status == OrderStatus.FILLED and filled != admitted_quantity)
    ):
        raise ExecutionUnavailable("Broker returned inconsistent fill receipt")
    return result


@dataclass(frozen=True)
class ReceiptFacts:
    zero_fill_rejection: bool
    zero_fill_refusal: bool
    open_order: bool
    terminal_order: bool
    complete_priced_fill: bool


def receipt_facts(result: OrderResult) -> ReceiptFacts:
    """Inspect a receipt without validating, normalizing or mutating it.

    Terminal orders may retain fills. A complete priced fill uses the router's
    existing native Decimal checks; numeric text accepted by execution validation
    does not become a priced fill through coercion here.
    """
    status, quantity, price = (
        result.status,
        result.filled_quantity,
        result.avg_fill_price,
    )
    return ReceiptFacts(
        zero_fill_rejection=status == OrderStatus.REJECTED and quantity == 0,
        zero_fill_refusal=(
            status in (OrderStatus.REJECTED, OrderStatus.CANCELLED) and quantity == 0
        ),
        open_order=status in (OrderStatus.SUBMITTED, OrderStatus.PARTIAL),
        terminal_order=status
        in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED),
        complete_priced_fill=(
            status == OrderStatus.FILLED
            and isinstance(quantity, Decimal)
            and quantity.is_finite()
            and quantity > 0
            and isinstance(price, Decimal)
            and price.is_finite()
            and price > 0
        ),
    )


@dataclass(frozen=True)
class FailureFacts:
    current_call_not_dispatched: bool | None
    outcome_unknown: bool | None
    definite_rejection: bool


def failure_facts(error: Exception) -> FailureFacts:
    """Interpret a reported execution failure, not all account-wide evidence.

    An unavailable call that did not dispatch may be blocked by an earlier
    uncertain attempt. Other exceptions establish neither rejection nor dispatch
    certainty. Separately observed submission evidence must still be preserved.
    Cancellation is control flow and remains outside callers' Exception handlers.
    """
    if isinstance(error, ExecutionUnavailable):
        unknown = bool(error.outcome_unknown)
        return FailureFacts(None if unknown else True, unknown, False)
    if isinstance(error, ExecutionRejected):
        return FailureFacts(True, False, True)
    return FailureFacts(None, None, False)
