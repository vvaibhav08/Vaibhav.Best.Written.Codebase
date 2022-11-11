#!/bin/bash
running_container_count=$(docker ps -a -q -f status=running | wc -l)
echo "Checking shutdown"
if [ "$running_container_count" == "0" ]; then
  echo "Shutting down now..."
  ZONE=$(gcloud compute instances list --filter="name=('$(hostname)')" --format 'csv[no-heading](zone)')
  docker container prune -f
  gcloud compute instances delete $(hostname) --zone=$ZONE -q
fi
