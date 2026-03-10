FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# El archivo data.json se guarda en /app/data.json dentro del contenedor
# Monta un volumen externo para persistencia: -v $(pwd)/data:/app

CMD ["python", "bot.py"]
