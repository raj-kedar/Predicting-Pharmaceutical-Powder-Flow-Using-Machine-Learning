# Placeholder container definition for AWS/Azure deployment.
# The serving entrypoint is added when app/ or api/ is implemented.
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY config/ config/
COPY api/ api/
COPY app/ app/
CMD ["python", "-c", "print('Serving entrypoint not implemented yet')"]
