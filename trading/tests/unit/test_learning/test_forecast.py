"""Tests for time series forecasting module."""

import numpy as np
import pytest
import torch

from learning.forecast import (
    DirectionalForecastModel,
    TimeSeriesDataset,
    TimeSeriesForecaster,
    ForecastOutput,
)


# ── DirectionalForecastModel ───────────────────────────────────────────────


class TestDirectionalForecastModel:
    def test_model_initialization(self):
        model = DirectionalForecastModel(input_size=5, hidden_size=32, num_layers=2)
        assert model.hidden_size == 32
        assert model.num_layers == 2

    def test_model_forward_shape(self):
        model = DirectionalForecastModel(input_size=5, hidden_size=32, num_layers=1)
        batch_size = 4
        seq_len = 60
        features = 5
        x = torch.randn(batch_size, seq_len, features)
        out = model(x)
        assert out.shape == (batch_size, 3)  # 3 classes


# ── TimeSeriesDataset ─────────────────────────────────────────────────────


class TestTimeSeriesDataset:
    def test_dataset_length(self):
        sequences = np.random.randn(10, 60, 5).astype(np.float32)
        targets = np.random.randint(0, 3, 10)
        dataset = TimeSeriesDataset(sequences, targets)
        assert len(dataset) == 10

    def test_dataset_getitem(self):
        sequences = np.random.randn(10, 60, 5).astype(np.float32)
        targets = np.random.randint(0, 3, 10)
        dataset = TimeSeriesDataset(sequences, targets)
        x, y = dataset[0]
        assert x.shape == (60, 5)
        assert isinstance(y.item(), int)


# ── TimeSeriesForecaster ───────────────────────────────────────────────────


class TestTimeSeriesForecaster:
    def test_forecaster_init(self):
        f = TimeSeriesForecaster(sequence_length=30, hidden_size=32, epochs=1)
        assert f.sequence_length == 30
        assert f.hidden_size == 32
        assert not f.is_trained

    def test_prepare_data_raises_on_short_data(self):
        f = TimeSeriesForecaster(sequence_length=60)
        with pytest.raises(ValueError, match="Need at least"):
            f._prepare_data([1.0] * 50, [1000.0] * 50)

    def test_prepare_data_returns_correct_shapes(self):
        f = TimeSeriesForecaster(sequence_length=10)
        close = list(range(50))
        vol = [1000.0] * 50
        ext = [{"signal": 0.1, "cvd": 0.2, "funding": 0.01}] * 50

        seqs, targets = f._prepare_data(close, vol, ext)

        # Should have (50 - 10) = 40 samples
        assert len(seqs) == 40
        assert seqs.shape == (40, 10, 5)  # (samples, seq_len, features)
        assert len(targets) == 40

    @pytest.mark.timeout(60)
    def test_train_returns_status(self):
        f = TimeSeriesForecaster(
            sequence_length=10,
            hidden_size=32,
            epochs=2,
            batch_size=8,
        )

        # Generate synthetic data
        t = np.linspace(0, 10, 100)
        close = (np.sin(t) * 10 + 100).tolist()
        vol = [1000.0] * 100
        ext = [{"signal": 0.1, "cvd": 0.2, "funding": 0.01}] * 100

        result = f.train(close, vol, ext)
        assert result["status"] == "trained"
        assert result["epochs"] == 2
        assert f.is_trained

    def test_predict_untrained_returns_neutral(self):
        f = TimeSeriesForecaster()
        result = f.predict([1.0] * 100, [1000.0] * 100)
        assert result.direction == "neutral"
        assert result.confidence == 0.33

    @pytest.mark.timeout(90)
    def test_train_and_predict(self):
        f = TimeSeriesForecaster(
            sequence_length=20,
            hidden_size=32,
            epochs=3,
            batch_size=16,
        )

        # Synthetic sine wave data with trend
        t = np.linspace(0, 20, 200)
        close = (np.sin(t) * 10 + t * 0.5 + 100).tolist()
        vol = [1000.0] * 200
        ext = [{"signal": 0.1, "cvd": 0.2, "funding": 0.01}] * 200

        # Train
        train_result = f.train(close, vol, ext)
        assert train_result["status"] == "trained"

        # Predict
        pred = f.predict(close[-50:], vol[-50:], ext[-50:])
        assert pred.direction in ("up", "down", "neutral")
        assert 0 <= pred.confidence <= 1.0

    def test_save_load_cycle(self, tmp_path):
        f = TimeSeriesForecaster(sequence_length=10, hidden_size=16, epochs=1)

        # Generate enough data to train
        close = (np.linspace(0, 10, 100) + 100).tolist()
        vol = [1000.0] * 100
        ext = [{"signal": 0.1, "cvd": 0.2, "funding": 0.01}] * 100

        f.train(close, vol, ext)

        # Save
        model_path = tmp_path / "forecast_model.pt"
        f.save(str(model_path))

        # Create new forecaster and load
        f2 = TimeSeriesForecaster(sequence_length=10, hidden_size=16)
        f2.load(str(model_path))

        assert f2.is_trained
        pred = f2.predict(close[-50:], vol[-50:], ext[-50:])
        assert pred.direction in ("up", "down", "neutral")
