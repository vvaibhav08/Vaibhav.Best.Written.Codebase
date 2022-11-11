#! /bin/bash
DOCKER_URL=******
CONCURRENCY=******
CELERY_BROKER_USERNAME=******
CELERY_BROKER_PASSWORD=******
CELERY_BROKER_URL=******
CELERY_BACKEND_URL=******
CELERY_BROKER=******
CELERY_RESULT_BACKEND=******
CELERY_HOST=******
QUEUE=******
VM_NAME_PREFIX==******

PIPELINE_OUTPUT_FOLDER=******

# Delete all cronjobs
crontab -r

# Let's cleanup docker first
docker container stop $(docker container ls -aq)
docker container rm $(docker container ls -aq)
docker container prune -f
docker system prune -f

# Authenticate with google
gcloud auth configure-docker --quiet
export PATH="/usr/lib/google-cloud-sdk/bin:$PATH"

# Pull docker image
docker pull $DOCKER_URL
# Run docker image
docker run -d --name $QUEUE -v /data:/data -v /flex_pipeline_data_accept:/flex_pipeline_data_accept -e VM_NAME=$(hostname) -e VM_NAME_PREFIX=$VM_NAME_PREFIX \
    -e PIPELINE_OUTPUT_FOLDER=$PIPELINE_OUTPUT_FOLDER \
    -e C_FORCE_ROOT=true -e CELERY_BROKER=$CELERY_BROKER -e CELERY_BROKER_URL=$CELERY_BROKER_URL -e CELERY_HOST=$CELERY_HOST  -e CELERY_BACKEND_URL=$CELERY_BACKEND_URL -e CELERY_BROKER_USERNAME=$CELERY_BROKER_USERNAME -e CELERY_BROKER_PASSWORD=$CELERY_BROKER_PASSWORD \
    $DOCKER_URL celery -A worker.app worker --hostname=$(hostname) --concurrency=$CONCURRENCY --pool=solo --prefetch-multiplier 1 --max-tasks-per-child=1 -Ofair --loglevel=info -Q $QUEUE --uid=nobody --gid=nogroup

# Download shutdown script
rm -f /tmp/shutdown_script.sh
touch /tmp/shutdown_script.sh
chmod +x /tmp/shutdown_script.sh
echo "#!/bin/bash" >> /tmp/shutdown_script.sh
echo "running_container_count=\$(docker ps -a -q -f status=running | wc -l)" >> /tmp/shutdown_script.sh
echo "echo \"Checking shutdown\"" >> /tmp/shutdown_script.sh
echo "if [ \"\$running_container_count\" == \"0\" ]; then" >> /tmp/shutdown_script.sh
echo "  echo \"Shutting down now...\"" >> /tmp/shutdown_script.sh
echo "  ZONE=\$(gcloud compute instances list --filter=\"name=('\$(hostname)')\" --format 'csv[no-heading](zone)')" >> /tmp/shutdown_script.sh
echo "  docker container prune -f" >> /tmp/shutdown_script.sh
echo "  gcloud compute instances delete \$(hostname) --zone=\$ZONE -q" >> /tmp/shutdown_script.sh
echo "fi" >> /tmp/shutdown_script.sh

# NOTE: Please make sure you have cron instaled on the image

# Add script to cron execution
crontab -r
crontab -l > mycron
cmd="*/1 * * * * sudo bash /tmp/shutdown_script.sh >/dev/null 2>&1"
# eval "sed -i '*shutdown_script.sh*' /var/spool/cron/crontabs/root"
echo "$cmd" >> mycron
crontab mycron
rm mycron
