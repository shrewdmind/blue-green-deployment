FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the watcher script
COPY watcher.py .

# Run watcher
CMD ["python", "watcher.py"]
