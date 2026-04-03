from risk.kill_switch import KillSwitch


class TestKillSwitch:
    def test_default_off(self):
        ks = KillSwitch()
        assert not ks.is_enabled

    def test_enable(self):
        ks = KillSwitch()
        ks.enable("max daily loss hit")
        assert ks.is_enabled
        assert ks.reason == "max daily loss hit"

    def test_disable(self):
        ks = KillSwitch()
        ks.enable("test")
        ks.disable()
        assert not ks.is_enabled
        assert ks.reason is None

    def test_toggle(self):
        ks = KillSwitch()
        ks.toggle(True, "activated")
        assert ks.is_enabled
        ks.toggle(False)
        assert not ks.is_enabled
