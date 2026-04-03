from decimal import Decimal
from datetime import datetime, date

from broker.models import OptionRight

def estimate_option_delta(
    underlying_price: Decimal, 
    strike: Decimal, 
    right: OptionRight, 
    expiry: date
) -> Decimal:
    """
    Crude MVP Delta estimator for option legs.
    Uses linear interpolation around ATM for simplicity without Black-Scholes.
    """
    if underlying_price == 0 or strike == 0:
        return Decimal("0")
        
    S = float(underlying_price)
    K = float(strike)
    ratio = S / K
    
    # Simple linear approx: S/K from 0.9 to 1.1 maps to Delta 0.0 to 1.0
    call_delta = max(0.0, min(1.0, 0.5 + (ratio - 1.0) * 5.0))
    
    if right == OptionRight.CALL:
        return Decimal(str(round(call_delta, 2)))
    else:
        # Put delta = Call delta - 1
        return Decimal(str(round(call_delta - 1.0, 2)))
