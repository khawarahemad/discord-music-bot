FROM python:3.10-slim

# Install FFmpeg and other dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . /app
WORKDIR /app

# Healthcheck (optional)
HEALTHCHECK CMD curl --fail http://localhost:8080 || exit 1

# Run the bot with Gunicorn (production WSGI server)
CMD ["gunicorn", "-b", "0.0.0.0:8080", "musify:app"]

