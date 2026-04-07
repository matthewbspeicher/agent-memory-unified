.PHONY: test test-unit test-integration test-docker test-parallel

# Run all tests (excludes live_paper and integration by default via pytest.ini)
test:
	python -m pytest tests/ -v --tb=short

# Run only unit tests
test-unit:
	python -m pytest tests/unit/ -v --tb=short

# Run tests in parallel (requires pytest-xdist)
test-parallel:
	python -m pytest tests/ -n auto -v --tb=short

# Run integration tests (requires running services)
test-integration:
	python -m pytest tests/integration/ -v --tb=short -m integration

# Run tests inside Docker container
test-docker:
	docker exec agent-memory-unified-trading-1 python -m pytest tests/ -v --tb=short
