import pytest
from pydantic import ValidationError
from config import Config

def test_pydantic_validation():
    # Should raise ValidationError for invalid type
    with pytest.raises(ValidationError):
        # We'll pass a string where an int is expected once migrated
        Config(api_port="invalid_port")
