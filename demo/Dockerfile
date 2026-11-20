FROM python:3.12-slim
RUN pip install --no-cache-dir requests==2.34.2
COPY cliente.py /cliente.py
CMD ["python", "-u", "/cliente.py"]
