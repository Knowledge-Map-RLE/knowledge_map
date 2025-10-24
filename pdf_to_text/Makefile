.PHONY: install proto run test clean docker-build docker-run help

help:
	@echo "Available commands:"
	@echo "  make install       - Install dependencies with Poetry"
	@echo "  make proto         - Generate protobuf files"
	@echo "  make run           - Run the gRPC service locally"
	@echo "  make test          - Run tests"
	@echo "  make clean         - Clean temporary files"
	@echo "  make docker-build  - Build Docker image"
	@echo "  make docker-run    - Run Docker container"

install:
	poetry install

proto:
	poetry run python -m grpc_tools.protoc \
		-I proto \
		--python_out=src/generated \
		--grpc_python_out=src/generated \
		proto/pdf_to_text.proto

run: proto
	poetry run python -m src.main

test:
	poetry run pytest

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf src/generated/*.py

docker-build:
	docker build -t pdf-to-text-service .

docker-run:
	docker run -p 8003:8003 --env-file .env pdf-to-text-service

