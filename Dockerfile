FROM python:3.12-slim

# Build tools for am4 C++ compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "am4 @ git+https://github.com/abc8747/am4.git@master" \
    && pip install --no-cache-dir -r requirements.txt

# Copy project code (changes more often, so this layer rebuilds)
COPY . .

# Dashboard port
EXPOSE 8000

# Default: launch dashboard
CMD ["python", "main.py", "dashboard"]
