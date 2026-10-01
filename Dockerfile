FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
EXPOSE 5006
CMD ["sh", "-c", "panel serve translator.py --address 0.0.0.0 --port ${PORT:-5006} --allow-websocket-origin='*'"]
