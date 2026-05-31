# Stage 1: build frontend (local build, no node image needed)
# Run: cd frontend && npm ci && npm run build  before docker build

# Runtime: Playwright + Python (pull from MCR, accessible from CN servers)
FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY vs.py config.py ./
COPY src/ ./src/
COPY plugin/ ./plugin/

# Copy pre-built frontend dist (built locally before docker build)
COPY frontend/dist ./frontend/dist

# Persistent data directories (mount as volumes)
RUN mkdir -p outputs projects inputs

EXPOSE 8000

ENV VUESCAN_HOST=0.0.0.0
ENV VUESCAN_PORT=8000

CMD ["python", "vs.py"]
