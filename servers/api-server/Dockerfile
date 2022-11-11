FROM tiangolo/uvicorn-gunicorn-fastapi:python3.8

# CMD /bin/sh

COPY ./servers/api-server/requirements.txt /requirements.txt

RUN pip install celery[redis]==5.1.2
RUN pip install -r /requirements.txt

# COPY ./credentials /credentials
COPY ./servers/api-server/src /app
COPY classes /app/classes
