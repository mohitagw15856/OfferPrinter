# OfferPrinter — isolated run image.
# Builds a small image that can run either the WebUI (default) or the CLI.
FROM python:3.11-slim

# Keep Python lean and predictable.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application.
COPY . .

# Streamlit serves on 8501.
EXPOSE 8501

# Provide your API key at run time, e.g.:
#   docker run -e ANTHROPIC_API_KEY=sk-... -p 8501:8501 offerprinter
# By default we launch the WebUI. To use the CLI instead, override the command:
#   docker run offerprinter python cli.py --help
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
