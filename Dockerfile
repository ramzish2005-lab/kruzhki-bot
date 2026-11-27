# Детерминированная сборка: не зависим от Railpack и его эвристик.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Сначала зависимости — слой кэшируется, пока не менялся requirements.txt.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Затем код.
COPY . .

# База живёт на volume (/data). Переменные DATA_DIR и DB_PATH задаются на хостинге.
CMD ["python", "run.py"]