FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8001 8002

CMD ["uvicorn", "cqrs.command_service.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
