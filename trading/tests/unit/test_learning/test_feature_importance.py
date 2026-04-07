"""Tests for Feature Importance Analyzer."""

import pytest
import numpy as np

from learning.feature_importance import (
    FeatureImportance,
    FeatureImportanceAnalyzer,
)


class TestFeatureImportanceAnalyzer:
    def test_init(self):
        features = ["price", "volume", "signal", "cvd", "funding"]
        analyzer = FeatureImportanceAnalyzer(features)

        assert analyzer.feature_names == features
        assert len(analyzer._history) == 0

    def test_analyze_from_attention(self):
        features = ["price", "volume", "signal"]
        analyzer = FeatureImportanceAnalyzer(features)

        # Simulated attention weights (time_steps=10, features=3)
        attention = np.random.rand(10, 3)
        attention = attention / attention.sum(axis=1, keepdims=True)  # Normalize

        importance = analyzer.analyze_from_attention(attention)

        assert len(importance.feature_names) == 3
        assert len(importance.importance_scores) == 3
        assert sum(importance.importance_scores) == pytest.approx(1.0, rel=0.01)

    def test_analyze_from_attention_multhead(self):
        features = ["price", "volume"]
        analyzer = FeatureImportanceAnalyzer(features)

        # Multi-head attention (4 heads, time_steps=5, features=2)
        attention = np.random.rand(4, 5, 2)

        importance = analyzer.analyze_from_attention(attention)

        assert len(importance.importance_scores) == 2

    def test_analyze_from_correlation(self):
        features = ["price", "volume", "signal"]
        analyzer = FeatureImportanceAnalyzer(features)

        # Create correlated data
        np.random.seed(42)
        X = np.random.randn(100, 3)
        X[:, 0] = X[:, 0] * 2 + X[:, 2] * 0.5  # price correlated with signal
        y = X[:, 0] + np.random.randn(100) * 0.1

        importance = analyzer.analyze_from_correlation(X, y)

        assert len(importance.importance_scores) == 3
        # Feature 0 should be most important (correlated with y)
        assert importance.importance_scores[0] >= importance.importance_scores[1]

    def test_analyze_from_shap(self):
        features = ["price", "volume", "signal"]
        analyzer = FeatureImportanceAnalyzer(features, importance_threshold=0.2)

        # Simulated SHAP values (100 samples, 3 features)
        shap_values = np.random.randn(100, 3)
        shap_values[:, 0] = shap_values[:, 0] * 2  # Double importance of feature 0

        importance = analyzer.analyze_from_shap(shap_values)

        assert len(importance.importance_scores) == 3
        # Feature 0 should have higher importance
        assert importance.importance_scores[0] > importance.importance_scores[1]

    def test_get_consensus_features(self):
        features = ["price", "volume", "signal"]
        analyzer = FeatureImportanceAnalyzer(features, importance_threshold=0.1)

        # Add multiple importance analyses where 'price' is top
        for _ in range(5):
            scores = [0.5, 0.3, 0.2]  # price always highest
            imp = FeatureImportance(
                feature_names=features,
                importance_scores=scores,
                top_features=["price", "volume"],  # Both above threshold
                timestamp="2024-01-01",
            )
            analyzer._history.append(imp)

        consensus = analyzer.get_consensus_features(window=5, min_stability=0.8)

        assert "price" in consensus

    def test_get_trending_features(self):
        features = ["price", "volume", "signal"]
        analyzer = FeatureImportanceAnalyzer(features)

        # Add history with decreasing importance for price
        analyzer._history.append(
            FeatureImportance(
                feature_names=features,
                importance_scores=[0.5, 0.3, 0.2],
                top_features=["price"],
                timestamp="2024-01-01",
            )
        )
        analyzer._history.append(
            FeatureImportance(
                feature_names=features,
                importance_scores=[0.4, 0.3, 0.3],
                top_features=["price", "volume"],
                timestamp="2024-01-02",
            )
        )
        analyzer._history.append(
            FeatureImportance(
                feature_names=features,
                importance_scores=[0.3, 0.4, 0.3],
                top_features=["volume"],
                timestamp="2024-01-03",
            )
        )

        trends = analyzer.get_trending_features()

        assert "price" in trends
        assert trends["price"] < 0  # Decreasing

    def test_suggest_pruning(self):
        features = ["price", "volume", "signal", "noise"]
        analyzer = FeatureImportanceAnalyzer(features, importance_threshold=0.1)

        # Add history with low importance for 'noise'
        imp = FeatureImportance(
            feature_names=features,
            importance_scores=[0.4, 0.3, 0.25, 0.05],  # noise is low
            top_features=["price", "volume", "signal"],
            timestamp="2024-01-01",
        )
        analyzer._history.append(imp)

        to_prune = analyzer.suggest_pruning(min_importance=0.1)

        assert "noise" in to_prune
        assert "price" not in to_prune


class TestFeatureImportance:
    def test_dataclass_fields(self):
        imp = FeatureImportance(
            feature_names=["a", "b"],
            importance_scores=[0.7, 0.3],
            top_features=["a"],
            timestamp="2024-01-01",
        )

        assert imp.feature_names == ["a", "b"]
        assert imp.importance_scores == [0.7, 0.3]
        assert imp.top_features == ["a"]
