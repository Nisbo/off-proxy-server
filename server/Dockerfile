ARG PYTHON_BASE=python:3.13-slim
FROM ${PYTHON_BASE}
ARG PYTHON_BASE
LABEL org.off-proxy.python-base=$PYTHON_BASE
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
COPY web ./web
ENV PYTHONUNBUFFERED=1
USER 65532:65532
CMD ["python", "app.py", "api"]
