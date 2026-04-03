from whatsapp.commands import parse_command, Command


def test_parse_portfolio():
    cmd = parse_command("/portfolio")
    assert cmd == Command(name="portfolio", args=[])


def test_parse_approve():
    cmd = parse_command("/approve opp-123")
    assert cmd == Command(name="approve", args=["opp-123"])


def test_parse_buy():
    cmd = parse_command("/buy AAPL 100")
    assert cmd == Command(name="buy", args=["AAPL", "100"])


def test_parse_case_insensitive():
    cmd = parse_command("/PORTFOLIO")
    assert cmd == Command(name="portfolio", args=[])


def test_parse_unknown_returns_none():
    cmd = parse_command("/foobar")
    assert cmd is None


def test_parse_not_a_command():
    cmd = parse_command("how's my portfolio?")
    assert cmd is None


def test_parse_help():
    cmd = parse_command("/help")
    assert cmd == Command(name="help", args=[])


def test_parse_start_agent():
    cmd = parse_command("/start rsi-scanner")
    assert cmd == Command(name="start", args=["rsi-scanner"])


def test_parse_stop_agent():
    cmd = parse_command("/stop rsi-scanner")
    assert cmd == Command(name="stop", args=["rsi-scanner"])


def test_parse_pnl_command():
    cmd = parse_command("/pnl rsi_scanner")
    assert cmd == Command(name="pnl", args=["rsi_scanner"])


def test_parse_trust_command():
    cmd = parse_command("/trust rsi_scanner assisted")
    assert cmd == Command(name="trust", args=["rsi_scanner", "assisted"])


def test_parse_optimize_command():
    cmd = parse_command("/optimize rsi_scanner")
    assert cmd == Command(name="optimize", args=["rsi_scanner"])


def test_parse_performance_command():
    cmd = parse_command("/performance")
    assert cmd == Command(name="performance", args=[])


def test_parse_tournament_command():
    cmd = parse_command("/tournament rsi_scanner")
    assert cmd == Command(name="tournament", args=["rsi_scanner"])
