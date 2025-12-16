# RAILWAY DEPLOYMENT - BOT ONLY
# This is explicitly for Railway to prevent API server from starting

FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ONLY RUN THE BOT - NOTHING ELSE
CMD ["python", "bot.py"]
