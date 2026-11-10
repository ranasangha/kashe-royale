# Kashe Royale — no dependencies, no build step. Only the Python 3 standard library.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY run.py ./
COPY pokerstack ./pokerstack
COPY web ./web

# Most hosts inject $PORT; run.py falls back to 8000 locally.
EXPOSE 8000

CMD ["python", "run.py", "--no-browser"]
