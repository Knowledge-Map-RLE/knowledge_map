FROM python:3.12-slim

WORKDIR /app

RUN pip install poetry --no-cache-dir

COPY pyproject.toml ./
RUN poetry config virtualenvs.create false && poetry install --no-dev --no-interaction --no-ansi

COPY . .

EXPOSE 50056

CMD ["poetry", "run", "python", "src/main.py"]
