# Test Suite

## Running Tests

### Unit Tests
```bash
pytest tests/ -v
```

### Integration Tests
```bash
pytest tests/ -v -m integration
```

### Coverage Report
```bash
pytest tests/ --cov=. --cov-report=html
```

### Bash Tests (BATS)
```bash
bats tests/test_discovery.sh
```

## Test Categories

1. **Unit Tests**: Test individual components in isolation
2. **Integration Tests**: Test component interactions
3. **Performance Tests**: Test system under load
4. **Failure Mode Tests**: Test error handling and recovery

## Test Coverage Goals

- Overall: ≥80%
- Critical paths: ≥90%
- API endpoints: 100%


