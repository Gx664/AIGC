FROM python:3.12-slim
WORKDIR /app
COPY dashboard.py dashboard_config.json ./
EXPOSE 8765
CMD ["python", "dashboard.py", "8765", "0.0.0.0"]
