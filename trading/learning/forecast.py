"""Lightweight time series forecasting for directional prediction.

A simplified deep learning model for time series forecasting:
- LSTM-based architecture (lighter than N-BEATS for quick training)
- Feature-rich input: price, volume, Bittensor signals, CVD, funding rates
- Directional forecast: up/down/neutral for ensemble integration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

logger = logging.getLogger(__name__)


@dataclass
class ForecastOutput:
    """Output from the forecasting model."""

    direction: str  # "up", "down", "neutral"
    confidence: float  # 0-1 confidence in the prediction
    price_change_pct: float  # Expected % change (placeholder)
    timestamp: datetime


class TimeSeriesDataset(Dataset):
    """PyTorch dataset for time series forecasting."""

    def __init__(self, sequences: np.ndarray, targets: np.ndarray):
        self.sequences = torch.FloatTensor(sequences)
        self.targets = torch.LongTensor(targets)

    def __len__(self) -> int:
        return len(self.sequences)

    def __getitem__(self, idx: int):
        return self.sequences[idx], self.targets[idx]


class DirectionalForecastModel(nn.Module):
    """LSTM-based directional forecaster.

    Input: sequence of (close, volume, signal, cvd, funding) = 5 features
    Output: 3-class classification (down, neutral, up)
    """

    def __init__(
        self,
        input_size: int = 5,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        forecast_len: int = 1,
    ):
        super().__init__()

        self.hidden_size = hidden_size
        self.num_layers = num_layers

        # LSTM encoder
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )

        # Attention-like pooling
        self.pool = nn.AdaptiveAvgPool1d(1)

        # Classification head
        self.head = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 3),  # 3 classes: down, neutral, up
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch, seq_len, features)
        lstm_out, _ = self.lstm(x)  # (batch, seq_len, hidden)

        # Pool across time dimension
        pooled = lstm_out.mean(dim=1)  # (batch, hidden)

        # Classification
        logits = self.head(pooled)
        return logits


class TimeSeriesForecaster:
    """LSTM-based forecaster for directional prediction.

    Supports training on historical data and generating predictions
    for integration with the ensemble.
    """

    def __init__(
        self,
        sequence_length: int = 60,  # Past 60 timesteps
        hidden_size: int = 64,
        num_layers: int = 2,
        learning_rate: float = 1e-3,
        batch_size: int = 32,
        epochs: int = 10,
    ):
        self.sequence_length = sequence_length
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.epochs = epochs

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model: DirectionalForecastModel | None = None
        self.is_trained = False

        logger.info(
            "TimeSeriesForecaster initialized: seq_len=%d, hidden=%d, device=%s",
            sequence_length,
            hidden_size,
            self.device,
        )

    def _prepare_data(
        self,
        close_prices: list[float],
        volumes: list[float],
        external_features: list[dict[str, float]] | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Prepare sequences and targets from raw data."""

        n = len(close_prices)
        min_required = self.sequence_length + 1

        if n < min_required:
            raise ValueError(f"Need at least {min_required} data points")

        # Default external features
        if external_features is None:
            external_features = [{"signal": 0, "cvd": 0, "funding": 0}] * n

        sequences = []
        targets = []

        for i in range(n - self.sequence_length):
            # Per-window normalization to avoid data leakage
            window_prices = close_prices[i : i + self.sequence_length]
            close_mean = np.mean(window_prices)
            close_std = max(np.std(window_prices), 1e-8)

            # Build sequence
            seq = []
            for j in range(self.sequence_length):
                # Normalized close
                close_norm = (close_prices[i + j] - close_mean) / close_std
                # Log volume (more stable)
                vol_log = np.log1p(volumes[i + j])
                # External features
                ext = external_features[i + j]
                signal = ext.get("signal", 0)
                cvd = ext.get("cvd", 0)
                funding = ext.get("funding", 0)

                seq.append([close_norm, vol_log, signal, cvd, funding])

            sequences.append(seq)

            # Target: direction of next price
            future_price = close_prices[i + self.sequence_length]
            current_price = close_prices[i + self.sequence_length - 1]
            pct_change = (future_price - current_price) / current_price

            # Threshold for direction
            if pct_change > 0.005:
                target = 2  # up
            elif pct_change < -0.005:
                target = 0  # down
            else:
                target = 1  # neutral

            targets.append(target)

        return np.array(sequences, dtype=np.float32), np.array(targets, dtype=np.int64)

    def train(
        self,
        close_prices: list[float],
        volumes: list[float],
        external_features: list[dict[str, float]] | None = None,
    ) -> dict[str, Any]:
        """Train the model on historical data."""

        logger.info("Training forecast model on %d samples", len(close_prices))

        # Prepare data
        sequences, targets = self._prepare_data(
            close_prices, volumes, external_features
        )

        # Create dataset and dataloader
        dataset = TimeSeriesDataset(sequences, targets)
        dataloader = DataLoader(
            dataset, batch_size=self.batch_size, shuffle=True, drop_last=True
        )

        # Initialize model
        self.model = DirectionalForecastModel(
            input_size=5,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
        ).to(self.device)

        # Loss and optimizer
        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.learning_rate)

        # Training loop
        self.model.train()
        total_loss = 0.0

        for epoch in range(self.epochs):
            epoch_loss = 0.0
            num_batches = 0

            for batch_x, batch_y in dataloader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)

                optimizer.zero_grad()
                outputs = self.model(batch_x)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item()
                num_batches += 1

            avg_loss = epoch_loss / max(num_batches, 1)
            total_loss += avg_loss
            logger.debug("Epoch %d/%d, loss: %.4f", epoch + 1, self.epochs, avg_loss)

        self.is_trained = True

        return {
            "status": "trained",
            "epochs": self.epochs,
            "avg_loss": total_loss / self.epochs,
            "samples": len(sequences),
        }

    def predict(
        self,
        close_prices: list[float],
        volumes: list[float],
        external_features: list[dict[str, float]] | None = None,
    ) -> ForecastOutput:
        """Generate directional forecast."""

        if not self.is_trained or self.model is None:
            return ForecastOutput(
                direction="neutral",
                confidence=0.33,
                price_change_pct=0.0,
                timestamp=datetime.now(),
            )

        # Need enough data
        if len(close_prices) < self.sequence_length:
            logger.warning("Not enough data for prediction")
            return ForecastOutput(
                direction="neutral",
                confidence=0.33,
                price_change_pct=0.0,
                timestamp=datetime.now(),
            )

        # Prepare last sequence
        close_prices = close_prices[-self.sequence_length - 1 :]
        volumes = volumes[-self.sequence_length - 1 :]
        if external_features:
            external_features = external_features[-self.sequence_length - 1 :]
        else:
            external_features = [{"signal": 0, "cvd": 0, "funding": 0}] * (
                self.sequence_length + 1
            )

        # Normalize
        close_mean = np.mean(close_prices[: self.sequence_length])
        close_std = max(np.std(close_prices[: self.sequence_length]), 1e-8)

        seq = []
        for j in range(self.sequence_length):
            close_norm = (close_prices[j] - close_mean) / close_std
            vol_log = np.log1p(volumes[j])
            ext = external_features[j]
            signal = ext.get("signal", 0)
            cvd = ext.get("cvd", 0)
            funding = ext.get("funding", 0)
            seq.append([close_norm, vol_log, signal, cvd, funding])

        seq = np.array([seq], dtype=np.float32)
        seq_tensor = torch.FloatTensor(seq).to(self.device)

        # Predict
        self.model.eval()
        with torch.no_grad():
            logits = self.model(seq_tensor)
            probs = torch.softmax(logits, dim=1)
            pred_class = torch.argmax(probs, dim=1).item()
            confidence = probs[0, pred_class].item()

        # Map to direction
        direction_map = {0: "down", 1: "neutral", 2: "up"}
        direction = direction_map[pred_class]

        return ForecastOutput(
            direction=direction,
            confidence=confidence,
            price_change_pct=0.0,
            timestamp=datetime.now(),
        )

    def save(self, path: str) -> None:
        """Save trained model."""
        if self.model:
            torch.save(self.model.state_dict(), path)
            logger.info("Model saved to %s", path)

    def load(self, path: str) -> None:
        """Load trained model."""
        self.model = DirectionalForecastModel(
            input_size=5,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
        ).to(self.device)
        self.model.load_state_dict(torch.load(path, map_location=self.device))
        self.model.eval()
        self.is_trained = True
        logger.info("Model loaded from %s", path)
