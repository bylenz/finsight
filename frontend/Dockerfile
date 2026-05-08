FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

RUN uv pip install --system -e .

EXPOSE 8501

CMD ["streamlit", "run", "src/finsight_ui/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
