import pytest
from config import Config


@pytest.mark.parametrize(
    "field,value",
    [
        ("paper_matching_interval_seconds", 0),
        ("paper_matching_interval_seconds", float("nan")),
        ("paper_matching_interval_seconds", 31),
        ("paper_matching_liquidity_per_quote", -1),
        ("paper_matching_liquidity_per_quote", float("inf")),
    ],
)
def test_invalid_paper_driver_configuration_is_rejected(field, value):
    with pytest.raises(ValueError):
        Config(**{field: value})
