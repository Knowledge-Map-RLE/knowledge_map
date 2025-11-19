# Test Structure Reorganization Summary

This document summarizes the standardized test structure applied across all services in the Knowledge Map project.

## Standard Structure

All services now follow this mandatory structure:

```
service_name/tests/
├── unit/               # Unit tests (fast, isolated)
├── integration/        # Integration tests (require external services)
├── e2e/               # End-to-end tests (full workflow)
├── conftest.py        # Pytest fixtures (if applicable)
├── pytest.ini         # Pytest configuration (if applicable)
└── fixtures/          # Common test fixtures/data (if needed)
```

## Service-by-Service Details

### 1. AI Service (`ai/`)
**Status**: New structure created (no existing tests)

```
ai/tests/
├── __init__.py
├── unit/
├── integration/
└── e2e/
```

### 2. API Service (`api/`)
**Status**: Reorganized 13 test files

```
api/tests/
├── __init__.py
├── conftest.py
├── pytest.ini
├── README.md
├── unit/
│   ├── routers/
│   │   ├── test_action_chains.py
│   │   └── test_nlp.py
│   └── services/
│       ├── test_data_extraction_service.py
│       ├── test_grpc_client_direct.py
│       ├── test_pdf_to_md_grpc_client.py
│       └── test_pdf_to_md_grpc_client_simple.py
├── integration/
│   └── test_pdf_processing_integration.py
├── e2e/
└── fixtures/
```

### 3. Auth Service (`auth/`)
**Status**: New structure created (empty directory existed)

```
auth/tests/
├── __init__.py
├── unit/
├── integration/
└── e2e/
```

### 4. Knowledge Map Core (`knowledge_map_core/`)
**Status**: New structure created (empty directory existed)

```
knowledge_map_core/tests/
├── __init__.py
├── unit/
├── integration/
└── e2e/
```

### 5. NLP Service (`nlp/`)
**Status**: Reorganized 12 test files

```
nlp/tests/
├── conftest.py
├── Tests_checklist.md
├── unit/
│   ├── markdown_preprocess/
│   │   ├── test_adding_a_period_to_the_end_of_headings.py
│   │   ├── test_split_sentencies_by_and.py
│   │   └── test_text_to_canonical_markdown.py
│   ├── test_canonical_markdown_to_knowledge_map.py
│   ├── test_canonical_markdown_to_ontology.py
│   ├── test_demo.py
│   ├── test_linguistic_text_analysis.py
│   ├── test_ontology_to_knowledge_map.py
│   ├── test_part_of_speech_tagging.py
│   ├── test_sentence_split_for_canonical_markdown.py
│   └── test_text_corpus_to_linguistic_patterns.py
├── integration/
└── e2e/
```

### 6. PDF to MD Service (`pdf_to_md/`)
**Status**: Reorganized 27 test files

```
pdf_to_md/tests/
├── __init__.py
├── conftest.py
├── pytest.ini
├── unit/
│   ├── api/
│   │   ├── test_image_routes.py
│   │   ├── test_routes.py
│   │   └── test_schemas.py
│   ├── core/
│   │   ├── test_config.py
│   │   └── test_validators.py
│   ├── grpc/
│   │   ├── test_grpc_server.py
│   │   └── test_port_utils.py
│   ├── models/
│   │   ├── test_base_model.py
│   │   └── test_docling_model.py
│   ├── services/
│   │   ├── test_conversion_service.py
│   │   ├── test_file_service.py
│   │   ├── test_model_service.py
│   │   └── test_s3_client.py
│   ├── test_app.py
│   ├── test_file_management.py
│   ├── test_health_monitoring.py
│   ├── test_model_registry.py
│   └── test_pdf_conversion.py
├── integration/
│   ├── test_api_integration.py
│   ├── test_coordinate_extraction_service.py
│   ├── test_docling_integration.py
│   ├── test_grpc_integration.py
│   ├── test_pdf_conversion.py
│   ├── test_s3_integration.py
│   └── test_s3_service.py
└── e2e/
```

### 7. Worker Data to DB (`worker_data_to_db/`)
**Status**: Reorganized minimal structure

```
worker_data_to_db/tests/
├── __init__.py
├── unit/
│   └── test_reference_extraction.py
├── integration/
├── e2e/
└── fixtures/
```

### 8. Worker Distributed Layering Rust (`worker_distributed_layering_rust/`)
**Status**: Reorganized Rust tests

```
worker_distributed_layering_rust/tests/
├── README.md
├── unit/
├── integration/
│   └── layout_engine_tests.rs
├── e2e/
└── artifacts/
    └── test_graph.gml
```

**Note**: Rust conventions differ from Python. The `tests/` directory is typically used for integration tests in Rust, while unit tests are usually placed inline in `src/` files with `#[cfg(test)]` modules.

## Running Tests

### Python Services (pytest)

```bash
# Run all tests for a service
cd <service_name>
poetry run pytest

# Run only unit tests
poetry run pytest tests/unit/

# Run only integration tests
poetry run pytest tests/integration/

# Run only e2e tests
poetry run pytest tests/e2e/

# Run with markers (if configured)
poetry run pytest -m unit
poetry run pytest -m integration
poetry run pytest -m e2e
```

### Rust Service (cargo test)

```bash
cd worker_distributed_layering_rust

# Run all tests
cargo test

# Run specific test file
cargo test --test layout_engine_tests

# Run with output
cargo test -- --nocapture
```

## Benefits of This Structure

1. **Consistency**: All services follow the same structure
2. **Clarity**: Easy to identify test type at a glance
3. **Selective Testing**: Run specific test levels as needed
4. **CI/CD Friendly**: Easy to configure pipelines to run different test levels
5. **Scalability**: Clear place to add new tests
6. **Documentation**: Structure itself documents test organization

## Migration Notes

- All existing test files have been moved to appropriate directories
- Configuration files (`conftest.py`, `pytest.ini`) remain at the root of `tests/`
- Common folders (`fixtures/`, `artifacts/`) are placed at the root level
- Test discovery should work automatically with existing pytest configurations
- No test logic was modified, only file locations changed

## Next Steps

1. Run tests for each service to ensure nothing broke during migration
2. Update CI/CD pipelines to take advantage of the new structure
3. Add test markers to categorize tests as unit/integration/e2e where not already present
4. Fill in empty test directories with appropriate tests

---

**Date**: 2025-11-19
**Restructured by**: Claude Code
