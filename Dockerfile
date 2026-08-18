# OfferPrinter — isolated run image.
# Builds a small image that can run either the web UI (default) or the CLI.
FROM python:3.12-slim

# Keep Python lean and predictable.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    OFFERPRINTER_NO_ANIM=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application and install it, so `offerprinter` is on PATH.
COPY . .
RUN pip install --no-cache-dir --no-deps -e .

# Streamlit serves on 8501.
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8501/_stcore/health')"

# Provide your API key at run time, e.g.:
#   docker run -e ANTHROPIC_API_KEY=sk-... -p 8501:8501 offerprinter
# By default we launch the web UI. To use the CLI instead, override the command:
#   docker run offerprinter offerprinter --help
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
