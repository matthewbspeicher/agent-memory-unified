import pytest

from strategies.base_guards import KillSwitchGuard


class _ActiveKillSwitch:
    is_enabled = True
    reason = "manual halt"


class _InactiveKillSwitch:
    is_enabled = False
    reason = None


@pytest.mark.asyncio
async def test_guard_blocks_when_kill_switch_enabled():
    guard = KillSwitchGuard(_ActiveKillSwitch())
    allowed = await guard.allow_scan("any_agent")
    assert allowed is False


@pytest.mark.asyncio
async def test_guard_allows_when_kill_switch_inactive():
    guard = KillSwitchGuard(_InactiveKillSwitch())
    allowed = await guard.allow_scan("any_agent")
    assert allowed is True


@pytest.mark.asyncio
async def test_guard_without_kill_switch_defaults_to_allow():
    guard = KillSwitchGuard(None)
    assert await guard.allow_scan("any_agent") is True
