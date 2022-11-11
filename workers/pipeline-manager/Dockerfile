FROM python:3.8

# Copy requirements
COPY ./workers/pipeline-manager/requirements.txt /tmp/requirements.txt

# Install requirements
RUN pip install celery[redis]==5.1.2
RUN pip --no-cache install -r /tmp/requirements.txt

# Make output directory
RUN mkdir -p /data/output

# Copy repo
COPY ./workers/pipeline-manager/src /app
WORKDIR /app
