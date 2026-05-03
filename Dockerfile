FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies for curl_cffi and cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libcurl4-openssl-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# py and depend
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Default port (Render uses 10000, HF Spaces uses 7860)
ENV PORT=10000
EXPOSE $PORT
CMD uvicorn main:app --host 0.0.0.0 --port $PORT