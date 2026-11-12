"""Order facts do not choose an Opportunity status or grant retry permission."""

from copy import deepcopy
from decimal import Decimal as D

import pytest

from broker.models import OrderResult, OrderStatus
from execution.outcome import (
    ExecutionRejected,
    ExecutionUnavailable,
    failure_facts,
    receipt_facts,
    validate_receipt,
)


@pytest.mark.parametrize(
    "status,quantity,price,open_order,terminal,refusal,priced",
    [
        (OrderStatus.SUBMITTED, D(0), None, True, False, False, False),
        (OrderStatus.PARTIAL, D(3), D(100), True, False, False, False),
        (OrderStatus.CANCELLED, D(3), D(100), False, True, False, False),
        (OrderStatus.CANCELLED, D(0), None, False, True, True, False),
        (OrderStatus.REJECTED, D(0), None, False, True, True, False),
        (OrderStatus.FILLED, D(3), D(100), False, True, False, True),
        (OrderStatus.FILLED, D(3), None, False, True, False, False),
        (OrderStatus.FILLED, D(3), D("NaN"), False, True, False, False),
        (OrderStatus.FILLED, D(3), D(0), False, True, False, False),
        (OrderStatus.FILLED, D(0), D(100), False, True, False, False),
        (OrderStatus.FILLED, "3", D(100), False, True, False, False),
        (OrderStatus.FILLED, D(3), "100", False, True, False, False),
    ],
)
def test_receipt_facts_keep_terminal_state_separate_from_usable_fills(
    status, quantity, price, open_order, terminal, refusal, priced
):
    result = OrderResult("known", status, quantity, price)
    facts = receipt_facts(result)
    assert facts.open_order is open_order
    assert facts.terminal_order is terminal
    assert facts.zero_fill_refusal is refusal
    assert facts.zero_fill_rejection is (status == OrderStatus.REJECTED)
    assert facts.complete_priced_fill is priced
    assert result.filled_quantity is quantity
    assert result.avg_fill_price is price


def test_validation_and_inspection_do_not_strengthen_each_other():
    raw = OrderResult("known", OrderStatus.FILLED, "3", D(100))
    original = deepcopy(raw)
    assert validate_receipt(raw, admitted_quantity=D(3)) is raw
    assert raw == original
    assert not receipt_facts(raw).complete_priced_fill
    no_price = OrderResult("known", OrderStatus.FILLED, D(3))
    assert validate_receipt(no_price, admitted_quantity=D(3)) is no_price
    assert not receipt_facts(no_price).complete_priced_fill
    # Inspection does not validate against an original proposal or throw away
    # evidence; the execution owner validates the actual admitted quantity.
    assert receipt_facts(
        OrderResult("known", OrderStatus.FILLED, D(3), D(100))
    ).complete_priced_fill


@pytest.mark.parametrize(
    "result,error,message",
    [
        (None, ExecutionUnavailable, "Broker returned no authoritative order receipt"),
        (
            OrderResult("", "UNKNOWN", True),
            ExecutionUnavailable,
            "Broker returned no authoritative order receipt",
        ),
        (
            OrderResult("known", "UNKNOWN", True),
            ExecutionUnavailable,
            "Broker returned unknown order status",
        ),
        (
            OrderResult("known", OrderStatus.FILLED, True),
            ExecutionRejected,
            "Invalid receipt filled quantity",
        ),
        (
            OrderResult("known", OrderStatus.FILLED, D(3)),
            ExecutionUnavailable,
            "Broker returned inconsistent fill receipt",
        ),
        (
            OrderResult("known", OrderStatus.PARTIAL, D(-1)),
            ExecutionUnavailable,
            "Broker returned inconsistent fill receipt",
        ),
    ],
)
def test_receipt_validation_retains_error_order_and_messages(result, error, message):
    with pytest.raises(error) as raised:
        validate_receipt(result, admitted_quantity=D(6))
    assert type(raised.value) is error
    assert str(raised.value) == message


def test_empty_id_zero_fill_rejection_still_returns_before_other_checks():
    result = OrderResult("", OrderStatus.REJECTED)
    assert validate_receipt(result, admitted_quantity=D(6)) is result


@pytest.mark.parametrize(
    "error,undispatched,unknown,rejected",
    [
        (ExecutionRejected("denied"), True, False, True),
        (ExecutionUnavailable("earlier attempt has the lock"), True, False, False),
        (ExecutionUnavailable("reply lost", outcome_unknown=True), None, True, False),
        (
            ExecutionUnavailable("truthy legacy flag", outcome_unknown="yes"),
            None,
            True,
            False,
        ),
        (RuntimeError("bookkeeping failed"), None, None, False),
        (TimeoutError("transport timeout"), None, None, False),
    ],
)
def test_failure_facts_preserve_exception_precedence_and_limits(
    error, undispatched, unknown, rejected
):
    facts = failure_facts(error)
    assert facts.current_call_not_dispatched is undispatched
    assert facts.outcome_unknown is unknown
    assert facts.definite_rejection is rejected


def test_existing_exception_imports_refer_to_the_identical_classes():
    from execution import service

    assert service.ExecutionRejected is ExecutionRejected
    assert service.ExecutionUnavailable is ExecutionUnavailable
    assert issubclass(ExecutionUnavailable, ExecutionRejected)
