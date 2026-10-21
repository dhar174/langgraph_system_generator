FROM python:3.11-slim

ARG LNF_INSTALL_GCP=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY setup.py README.md ./ 
COPY src ./src
COPY data ./data
COPY docs ./docs

RUN if [ "$LNF_INSTALL_GCP" = "true" ]; then pip install --no-cache-dir '.[gcp]'; else pip install --no-cache-dir .; fi

EXPOSE 8000

CMD ["uvicorn", "langgraph_system_generator.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "3"]
