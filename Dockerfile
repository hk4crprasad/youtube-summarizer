FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create required directories
RUN mkdir -p temp downloads instance

# Basic environment variables
ENV FLASK_APP=main.py
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

COPY pytubefix_tokens.json /usr/local/lib/python3.11/site-packages/pytubefix/__cache__/tokens.json

# Expose port for Cloud Run
EXPOSE 8080

# Run your app
CMD ["python", "main.py"]
