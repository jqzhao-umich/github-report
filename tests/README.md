# Test Suite Documentation

This directory contains comprehensive tests for the GitHub Report MCP Server application.

## Test Structure

### Test Files

- **test_server.py** - Tests for the main FastAPI server (server.py)
  - Root endpoint tests
  - GitHub report API endpoint tests
  - Iteration info retrieval tests
  - MCP server tools, resources, and prompts tests

- **test_core_agent.py** - Tests for the core agent
  - Resource operations (list, read)
  - Prompt operations (list, get)
  - Tool operations (add-note)
  - Integration tests
  - Error handling

- **test_github_agent.py** - Basic tests for GitHub agent
- **test_github_agent_enhanced.py** - Enhanced tests for GitHub agent with mocking
  - Tool listing tests
  - Iteration info retrieval tests
  - GitHub data retrieval tests
  - Error handling tests

- **test_web_interface.py** - Tests for web interface agent
- **test_web_interface_enhanced.py** - Enhanced web interface tests (if created)

- **test_main_coordinator.py** - Tests for main coordinator agent
  - Tool listing tests
  - Report generation workflow tests
  - Error handling tests
  - Agent communication tests

- **test_utils.py** - Tests for utility functions
  - Timezone utilities
  - Environment variable utilities
  - Datetime formatting utilities

- **test_integration.py** - Integration tests
- **test_performance.py** - Performance and benchmark tests

- **test_base.py** - Base agent tests

### Shared Fixtures

- **conftest.py** - Shared pytest fixtures and configuration
  - Mock GitHub tokens and credentials
  - Mock GitHub objects (users, orgs, repos)
  - Mock iteration info
  - Mock GitHub data
  - MCP session mocks

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/test_server.py
pytest tests/test_core_agent.py
pytest tests/test_github_agent_enhanced.py
```

### Run Tests by Marker

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only performance tests
pytest -m performance

# Run tests that don't require network
pytest -m "not network"

# Skip slow tests
pytest -m "not slow"
```

### Run Tests with Coverage

```bash
# Generate coverage report
pytest --cov=agent_mcp_demo --cov-report=term-missing

# Generate HTML coverage report
pytest --cov=agent_mcp_demo --cov-report=html

# Generate XML coverage report (for CI)
pytest --cov=agent_mcp_demo --cov-report=xml
```

### Run Tests Verbosely

```bash
pytest -v

# Show print statements
pytest -s

# Show local variables on failure
pytest -l
```

### Run Specific Test Function

```bash
pytest tests/test_server.py::TestRootEndpoint::test_root_endpoint_returns_html
```

## Test Categories

### Unit Tests

Unit tests test individual components in isolation:
- `test_utils.py` - Utility function tests
- `test_core_agent.py` - Core agent unit tests
- Parts of `test_server.py` - Server component tests

### Integration Tests

Integration tests test multiple components working together:
- `test_integration.py` - Full workflow tests
- Parts of `test_main_coordinator.py` - Coordinator workflow tests

### Performance Tests

Performance tests measure and benchmark performance:
- `test_performance.py` - Performance benchmarks

### API Tests

API tests test the FastAPI endpoints:
- `test_server.py` - Server endpoint tests
- `test_web_interface.py` - Web interface tests

## Mocking Strategy

The test suite uses extensive mocking to:
1. **Avoid external API calls** - GitHub API calls are mocked
2. **Isolate components** - Each component is tested independently
3. **Control test environment** - Environment variables are mocked
4. **Speed up tests** - No network delays

### Common Mocks

- **GitHub API** - PyGithub library is mocked
- **HTTP requests** - requests and httpx are mocked
- **Environment variables** - Using pytest's monkeypatch
- **MCP sessions** - AsyncMock for MCP server sessions

## Writing New Tests

### Test Naming Convention

- Test files: `test_*.py`
- Test classes: `Test*`
- Test functions: `test_*`

### Test Structure

```python
import pytest
from unittest.mock import Mock, patch

class TestFeature:
    """Tests for a specific feature"""
    
    @pytest.mark.asyncio
    async def test_feature_success(self):
        """Test successful feature operation"""
        # Arrange
        # Act
        # Assert
        pass
    
    def test_feature_error_handling(self):
        """Test error handling"""
        with pytest.raises(ValueError):
            # Code that should raise error
            pass
```

### Using Fixtures

```python
def test_with_fixture(mock_github_token, mock_org_name):
    """Test using fixtures from conftest.py"""
    # Use the fixtures
    pass
```

### Marking Tests

```python
@pytest.mark.integration
def test_integration():
    """Mark test as integration test"""
    pass

@pytest.mark.slow
def test_slow_operation():
    """Mark test as slow"""
    pass

@pytest.mark.network
def test_network_operation():
    """Mark test as requiring network"""
    pass
```

## Test Coverage Goals

- **Unit Tests**: > 80% coverage
- **Integration Tests**: All critical workflows
- **API Tests**: All endpoints
- **Error Handling**: All error paths

## Continuous Integration

Tests are designed to run in CI environments:
- No external dependencies required
- Fast execution
- Deterministic results
- Comprehensive error reporting

## Troubleshooting

### Tests Fail Due to Missing Imports

Ensure the Python path includes the `src` directory:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
```

### Tests Fail Due to Missing Environment Variables

Tests should mock environment variables. If you see failures, check that fixtures are being used correctly.

### Async Test Issues

Make sure async tests use `@pytest.mark.asyncio` decorator and `pytest-asyncio` is installed.

### Mock Not Working

Check that you're patching the correct import path. Use `patch('module.path.function')` where `module.path` is the import path in the file being tested.

## Best Practices

1. **Isolate tests** - Each test should be independent
2. **Use fixtures** - Share common setup code
3. **Mock external dependencies** - Don't make real API calls
4. **Test error cases** - Test both success and failure paths
5. **Keep tests fast** - Mock slow operations
6. **Write descriptive names** - Test names should describe what they test
7. **Document complex tests** - Add docstrings for complex test logic
