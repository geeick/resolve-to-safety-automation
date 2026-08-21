FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps chromium

COPY . .

CMD streamlit run shift_report_web_app_v23_pricing_suggestions.py \
    --server.address=0.0.0.0 \
    --server.port=$PORT