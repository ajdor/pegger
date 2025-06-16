FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py ./

EXPOSE 4000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:4000", "server:app"]
