FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data/uploads
EXPOSE 8000

# Demo data is optional and is not baked into the image, because the data
# folder is a mounted volume. Load it with:
#   docker compose run --rm invoice-dashboard python seed_demo.py --reset
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
