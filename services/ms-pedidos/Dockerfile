FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
# Segurança: o processo NÃO roda como root dentro do container
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 5001
CMD ["python", "app.py"]
