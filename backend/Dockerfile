FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts

EXPOSE 8000
# --proxy-headers makes uvicorn read X-Forwarded-For, so the rate limiter keys on the
# real client rather than the proxy. Without it every user behind the load balancer
# shares one address and a single script exhausts the login limit for everybody.
# FORWARDED_ALLOW_IPS should name the proxy's address range at deploy time; it is
# deliberately not "*", which would let any client spoof its own address.
ENV FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
