import numpy as np
import pandas as pd
import pytest


class TestStableRegimeDetector:
    def test_initial_state_none(self):
        from intelligence.providers.regime import StableRegimeDetector

        detector = StableRegimeDetector(min_state_duration=3)
        assert detector.current_state is None

    def test_state_set_after_duration(self):
        from intelligence.providers.regime import StableRegimeDetector

        detector = StableRegimeDetector(min_state_duration=3)
        for _ in range(3):
            state, changed = detector.update(0)
        assert detector.current_state == 0

    def test_no_flip_before_duration(self):
        from intelligence.providers.regime import StableRegimeDetector

        detector = StableRegimeDetector(min_state_duration=3)
        for _ in range(3):
            detector.update(0)
        state, changed = detector.update(1)
        assert state == 0
        assert changed is False

    def test_flip_after_sustained_change(self):
        from intelligence.providers.regime import StableRegimeDetector

        detector = StableRegimeDetector(min_state_duration=3)
        for _ in range(3):
            detector.update(0)
        for _ in range(3):
            state, changed = detector.update(1)
        assert detector.current_state == 1
        assert changed is True


class TestRegimeStateMapping:
    def test_state_names(self):
        from intelligence.providers.regime import REGIME_STATES

        assert REGIME_STATES[0] == "trending_bull"
        assert REGIME_STATES[1] == "trending_bear"
        assert REGIME_STATES[2] == "volatile"
        assert REGIME_STATES[3] == "quiet"


class TestHMMFeatureExtraction:
    def test_extract_features_shape(self):
        from intelligence.providers.regime import extract_hmm_features

        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        df = pd.DataFrame(
            {
                "close": 50000 + np.cumsum(np.random.randn(100) * 500),
                "volume": np.random.uniform(1e9, 5e9, 100),
            },
            index=dates,
        )
        df["funding_rate"] = 0.001
        features = extract_hmm_features(df)
        assert features.shape[1] == 4
        assert features.shape[0] < 100
        assert not np.isnan(features).any()
