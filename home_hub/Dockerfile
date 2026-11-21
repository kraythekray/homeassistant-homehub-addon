FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY backend ./backend
COPY static ./static
WORKDIR /app/backend
EXPOSE 8099
CMD ["python", "-m", "homehub.main"]
