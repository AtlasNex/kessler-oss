FROM python:3.11-slim
WORKDIR /app
COPY orchestrator.py store.py ./
ENV DRILL_PORT=8095
EXPOSE 8095
CMD ["python", "orchestrator.py"]
