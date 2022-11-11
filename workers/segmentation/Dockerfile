FROM eu.gcr.io/sobolt-plantfellow/plantfellow.flex.segmentation:latest

# Copy requirements
COPY ./workers/segmentation/requirements.txt /tmp/requirements.txt

# Install requirements
RUN pip install celery[redis]==5.1.2
RUN pip --no-cache install -r /tmp/requirements.txt

# Copy repo
COPY ./workers/segmentation/src /app

WORKDIR /app

RUN chown -R nobody:nogroup /app
