FROM python:3.8-slim-buster

# Copy requirements
COPY ./servers/vm-manager/requirements.txt /tmp/requirements.txt
# Install requirements-
RUN pip install --no-cache-dir --upgrade -r /tmp/requirements.txt
# Copy repo
COPY ./servers/vm-manager/src /app
WORKDIR /app

# Default to running main_db_cpu.py
CMD ["sh", "-c", "python -u manage_vms.py"]
