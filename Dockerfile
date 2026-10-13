FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[app]"
COPY . .

EXPOSE 8501
# Si no hay modelo entrenado, genera la demo antes de levantar el dashboard
CMD ["sh", "-c", "[ -f modelos/modelo.joblib ] || python -m demanda.pipeline demo; streamlit run app/dashboard.py --server.address=0.0.0.0"]
