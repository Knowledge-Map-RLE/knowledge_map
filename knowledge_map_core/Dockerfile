FROM python:3.12-slim

WORKDIR /app

RUN pip install poetry --no-cache-dir

COPY --from=shared ./knowledge ../shared/knowledge
COPY --from=shared ./model_registry ../shared/model_registry
COPY pipeline ./pipeline
COPY --from=config ./config/models.toml ./config/models.toml
COPY pyproject.toml ./
RUN poetry config virtualenvs.create false && poetry install --only main --no-root --no-interaction --no-ansi

COPY . .

EXPOSE 50056
ENV PYTHONPATH=/shared/model_registry

CMD ["poetry", "run", "python", "src/main.py"]
