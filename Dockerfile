FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py dashboard.py control.py security.py ./
COPY web ./web
ENV PYTHONUNBUFFERED=1
CMD ["python", "app.py", "api"]
