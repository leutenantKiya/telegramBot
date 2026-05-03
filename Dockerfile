FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies for curl_cffi and cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libcurl4-openssl-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (Docker cache optimization)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# port used in the project
EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]