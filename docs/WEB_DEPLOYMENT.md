# Web Interface Deployment Guide

The LangGraph System Generator includes a modern web interface built with FastAPI, HTML, CSS, and JavaScript. This guide covers various deployment options.

## Quick Start

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Start the server:
```bash
export LNF_OUTPUT_BASE=$(pwd)  # Set output base directory
uvicorn langgraph_system_generator.api.server:app --host 0.0.0.0 --port 8000 --reload
```

3. Open your browser to: `http://localhost:8000`

### Docker Deployment

Build and run with Docker:

```bash
docker build -t langgraph-system-generator .
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=your_api_key_here \
  -v $(pwd)/output:/app/output \
  langgraph-system-generator
```

Then access at: `http://localhost:8000`

## Deployment Options

### Option 1: Traditional Cloud Hosting

Deploy to any cloud provider that supports Python web applications:

#### Heroku
```bash
# Install Heroku CLI, then:
heroku create your-app-name
git push heroku main
heroku open
```

#### AWS EC2
1. Launch an EC2 instance
2. Install Python and dependencies
3. Run uvicorn with systemd or supervisord
4. Configure nginx as reverse proxy

#### DigitalOcean
1. Create a Droplet
2. Clone repository
3. Set up Python environment
4. Run with uvicorn + nginx

### Option 2: Serverless (AWS Lambda + API Gateway)

Use Mangum to wrap the FastAPI app:

```python
from mangum import Mangum
from langgraph_system_generator.api.server import app

handler = Mangum(app)
```

Deploy with AWS SAM or Serverless Framework.

### Option 3: Container Orchestration

#### Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: langgraph-generator
spec:
  replicas: 3
  selector:
    matchLabels:
      app: langgraph-generator
  template:
    metadata:
      labels:
        app: langgraph-generator
    spec:
      containers:
      - name: api
        image: langgraph-system-generator:latest
        ports:
        - containerPort: 8000
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: api-secrets
              key: openai-key
```

#### Docker Compose
```yaml
version: '3.8'
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - LNF_OUTPUT_BASE=/app/output
    volumes:
      - ./output:/app/output
```

### Option 4: Platform-as-a-Service (PaaS)

#### Railway
1. Connect your GitHub repository
2. Railway auto-detects the Python app
3. Add environment variables in dashboard
4. Deploy automatically on push

#### Render
1. Connect repository
2. Select "Web Service"
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `uvicorn langgraph_system_generator.api.server:app --host 0.0.0.0 --port $PORT`

#### Fly.io
```bash
fly launch
fly deploy
```

### Option 5: GitHub Codespaces

The repository is ready to use with GitHub Codespaces:

1. Click "Code" → "Open with Codespaces"
2. Codespace starts with all dependencies
3. Run: `uvicorn langgraph_system_generator.api.server:app --host 0.0.0.0 --port 8000`
4. Access via forwarded port

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (required for live mode) | - |
| `LNF_OUTPUT_BASE` | Base directory for output files | `.` |
| `VECTOR_STORE_PATH` | Path to vector store | `./data/vector_store` |
| `DEFAULT_MODEL` | Default LLM model | `gpt-4-turbo-preview` |

## Security Considerations

### Production Deployment

1. **Use HTTPS**: Always deploy with SSL/TLS certificates
2. **Rate Limiting**: Implement rate limiting to prevent abuse
3. **Authentication**: Add authentication for production use
4. **API Keys**: Store secrets in environment variables, not code
5. **Output Directory**: Restrict output directory paths to prevent directory traversal

### Example with Rate Limiting

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/generate")
@limiter.limit("5/minute")
async def generate_notebook(request: Request, ...):
    ...
```

## Monitoring and Logging

### Health Checks

The `/health` endpoint provides basic health status:

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### Application Monitoring

Integrate with monitoring services:
- **Sentry** for error tracking
- **DataDog** for metrics and logs
- **New Relic** for APM
- **Prometheus** for metrics collection

### Logging

Configure structured logging:

```python
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
```

## Scaling Considerations

1. **Horizontal Scaling**: Run multiple instances behind a load balancer
2. **Async Processing**: Use Celery or background tasks for long-running generations
3. **Caching**: Cache common patterns and documentation lookups
4. **CDN**: Serve static files (CSS, JS) via CDN
5. **Database**: Consider persistent storage for generation history

## Troubleshooting

### Common Issues

**Server won't start:**
- Check all dependencies are installed: `pip install -r requirements.txt`
- Verify port 8000 is available: `lsof -i :8000`
- Check environment variables are set

**Generation fails:**
- Verify output directory permissions
- Check API keys for live mode
- Review server logs for errors

**Static files not loading:**
- Ensure static directory exists: `src/langgraph_system_generator/api/static/`
- Check FastAPI static file mounting
- Verify file paths in HTML

## Support

For issues and questions:
- GitHub Issues: https://github.com/dhar174/langgraph_system_generator/issues
- Documentation: See `docs/` directory
