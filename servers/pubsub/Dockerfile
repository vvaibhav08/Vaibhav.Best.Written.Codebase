FROM python:3.8

# Copy requirements
COPY ./servers/pubsub/requirements.txt /tmp/requirements.txt

# Install requirements
RUN pip install celery[redis]==5.1.2
RUN pip install -r /tmp/requirements.txt

# Copy repo
COPY ./servers/pubsub/src /app
# COPY classes /app/classes
WORKDIR /app

# # Default to run pubsub_listener
# CMD [   "/bin/sh",                  \
#         "-c",                       \
#         "watchmedo auto-restart     \
#             --directory=/app        \
#             --pattern=*.py          \
#             --recursive             \
#             -- python -u main.py"]
