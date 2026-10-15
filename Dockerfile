# Container image for deploying the Admission Enquiry Assistant
# (used for local container testing and as the Elastic Beanstalk "Docker platform" artifact)
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py ai_engine.py data_pipeline.py security.py ./
COPY knowledge_base.json .
COPY templates/ templates/
COPY static/ static/

# Run the WSGI application with gunicorn (3 workers, timeout tuned for GPT API calls)
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 3 --timeout 60 application:application"]
