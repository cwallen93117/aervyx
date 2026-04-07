FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml /app/
RUN apt-get update && apt-get install -y --no-install-recommends libeccodes-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade pip && pip install -e .

COPY . /app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]