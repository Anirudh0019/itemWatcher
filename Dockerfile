FROM python:3.12-slim

# Install system deps for Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdbus-1-3 libdrm2 libxkbcommon0 libatspi2.0-0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -e . \
    && playwright install chromium

# Copy application code
COPY . .

# Re-install in editable mode with full source
RUN pip install --no-cache-dir -e .

# Create data directory
RUN mkdir -p /data

ENV ITEMWATCHER_DB_PATH=/data/data.db
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
