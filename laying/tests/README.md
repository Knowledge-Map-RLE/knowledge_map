# Test Structure

This test directory follows the standardized structure:

- `unit/` - Unit tests (fast, isolated tests for individual components)
- `integration/` - Integration tests (tests that verify multiple components working together)
- `e2e/` - End-to-end tests (full workflow tests)
- `artifacts/` - Test artifacts and output files

## Running Tests

```bash
# Run all tests
cargo test

# Run only integration tests
cargo test --test '*' --test-threads=1

# Run specific test file
cargo test --test layout_engine_tests
```

## Note on Rust Testing Conventions

In Rust, the `tests/` directory is conventionally used for integration tests by default. Unit tests are typically placed inline within `src/` files using `#[cfg(test)]` modules. This structure adapts to the project-wide testing organization while maintaining Rust idioms.
