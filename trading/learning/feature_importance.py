"""Automated feature importance using TFT attention weights.

Uses the Temporal Fusion Transformer model's attention mechanism
to identify which features matter most for predictions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FeatureImportance:
    """Importance scores for features."""

    feature_names: list[str]
    importance_scores: list[float]  # 0-1 normalized
    top_features: list[str]  # Features above threshold
    timestamp: str


class FeatureImportanceAnalyzer:
    """Analyze feature importance from model attention weights.

    For TFT-style models, attention weights reveal which time steps
    and features matter most. For other models, uses SHAP values.
    """

    def __init__(
        self,
        feature_names: list[str],
        importance_threshold: float = 0.1,
    ):
        self.feature_names = feature_names
        self.importance_threshold = importance_threshold
        self._history: list[FeatureImportance] = []

    def analyze_from_attention(
        self,
        attention_weights: np.ndarray,
        time_steps: int | None = None,
    ) -> FeatureImportance:
        """Analyze feature importance from attention weights.

        Args:
            attention_weights: Shape (num_heads, time_steps, features) or (time_steps, features)
            time_steps: Number of time steps in the input (for parsing if needed)

        Returns:
            FeatureImportance with scores
        """
        # Average across heads if multi-head
        if len(attention_weights.shape) == 3:
            weights = attention_weights.mean(axis=0)  # (time_steps, features)
        else:
            weights = attention_weights

        # Average across time to get feature importance
        feature_importance = weights.mean(axis=0)  # (features,)

        # Normalize to sum to 1
        if feature_importance.sum() > 0:
            feature_importance = feature_importance / feature_importance.sum()

        # Identify top features
        top_idx = np.where(feature_importance > self.importance_threshold)[0]
        top_features = [self.feature_names[i] for i in top_idx]

        importance = FeatureImportance(
            feature_names=self.feature_names,
            importance_scores=feature_importance.tolist(),
            top_features=top_features,
            timestamp=np.datetime64("now").astype(str),
        )

        self._history.append(importance)
        return importance

    def analyze_from_shap(
        self,
        shap_values: np.ndarray,
    ) -> FeatureImportance:
        """Analyze feature importance from SHAP values.

        Args:
            shap_values: Shape (num_samples, features) - SHAP value magnitudes

        Returns:
            FeatureImportance with scores
        """
        # Mean absolute SHAP value across samples
        mean_abs_shap = np.abs(shap_values).mean(axis=0)

        # Normalize to sum to 1
        if mean_abs_shap.sum() > 0:
            mean_abs_shap = mean_abs_shap / mean_abs_shap.sum()

        # Identify top features
        top_idx = np.where(mean_abs_shap > self.importance_threshold)[0]
        top_features = [self.feature_names[i] for i in top_idx]

        importance = FeatureImportance(
            feature_names=self.feature_names,
            importance_scores=mean_abs_shap.tolist(),
            top_features=top_features,
            timestamp=np.datetime64("now").astype(str),
        )

        self._history.append(importance)
        return importance

    def analyze_from_correlation(
        self,
        X: np.ndarray,
        y: np.ndarray,
    ) -> FeatureImportance:
        """Analyze feature importance from correlation with target.

        Args:
            X: Feature matrix (samples, features)
            y: Target values (samples,)

        Returns:
            FeatureImportance with scores
        """
        n_features = X.shape[1]
        correlations = []

        for i in range(n_features):
            corr = np.abs(np.corrcoef(X[:, i], y)[0, 1])
            if np.isnan(corr):
                corr = 0.0
            correlations.append(corr)

        correlations_arr = np.array(correlations)

        # Normalize
        if correlations_arr.sum() > 0:
            correlations_arr = correlations_arr / correlations_arr.sum()

        top_idx = np.where(correlations_arr > self.importance_threshold)[0]
        top_features = [self.feature_names[i] for i in top_idx]

        importance = FeatureImportance(
            feature_names=self.feature_names,
            importance_scores=correlations_arr.tolist(),
            top_features=top_features,
            timestamp=np.datetime64("now").astype(str),
        )

        self._history.append(importance)
        return importance

    def get_consensus_features(
        self,
        window: int = 5,
        min_stability: float = 0.7,
    ) -> list[str]:
        """Get features that are consistently important.

        Args:
            window: Number of recent analyses to consider
            min_stability: Minimum ratio of times feature was top

        Returns:
            List of consensus feature names
        """
        if len(self._history) < 2:
            return []

        # Look at recent analyses
        recent = self._history[-window:]

        feature_counts: dict[str, int] = {}
        for imp in recent:
            for feature in imp.top_features:
                feature_counts[feature] = feature_counts.get(feature, 0) + 1

        # Features that are top in >= min_stability fraction
        threshold_count = int(len(recent) * min_stability)
        consensus = [
            f for f, count in feature_counts.items() if count >= threshold_count
        ]

        return sorted(consensus, key=lambda f: feature_counts[f], reverse=True)

    def get_trending_features(self) -> dict[str, float]:
        """Get features whose importance is increasing or decreasing.

        Returns:
            Dict of feature -> trend direction (+1 increasing, -1 decreasing, 0 stable)
        """
        if len(self._history) < 3:
            return {}

        # Compare recent to older
        recent = self._history[-1].importance_scores
        older = self._history[-3].importance_scores

        trends = {}
        for i, name in enumerate(self.feature_names):
            if i < len(recent) and i < len(older):
                diff = recent[i] - older[i]
                if diff > 0.05:
                    trends[name] = 1.0
                elif diff < -0.05:
                    trends[name] = -1.0
                else:
                    trends[name] = 0.0

        return trends

    def suggest_pruning(
        self,
        min_importance: float = 0.05,
    ) -> list[str]:
        """Suggest features to prune (low importance).

        Returns:
            List of feature names to potentially remove
        """
        if not self._history:
            return []

        # Use most recent analysis
        recent = self._history[-1]

        to_prune = []
        for name, score in zip(recent.feature_names, recent.importance_scores):
            if score < min_importance:
                to_prune.append(name)

        return to_prune
