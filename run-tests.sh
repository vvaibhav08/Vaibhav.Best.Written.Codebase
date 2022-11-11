# #!/usr/bin/bash

FAILURE=0  # 0 means 0, anything but 0 is a failure code

# Log whether containers are already running and start them if they aren't
echo "Ensuring services are running"
RUNNING=`docker-compose -f docker-compose-dev.yml ps -q`
export ENVPATH="./template_env.env"
ENVPATH=$ENVPATH docker-compose -f docker-compose-dev.yml --profile local_dev --env-file $ENVPATH up --build
FAILURE=$?
if [[ ! $FAILURE -eq "0" ]]; then exit $FAILURE; fi
echo

# Do tests
echo "Start tests"
SERVICES="flex-measuring"
for SERVICE in $SERVICES; do
    echo Testing $SERVICE

    # Check if service is running
    CONTAINER=`docker-compose ps -q $SERVICE`
    if [[ -z $CONTAINER ]]; then FAILURE=1; fi

    # Static analysis with Mypy (including dependencies)
    docker-compose -f docker-compose-dev.yml exec -T $SERVICE bash -c 'mypy --config-file /tests/mypy.ini /app'; (( FAILURE=$FAILURE | $? ))

    # Run unit tests
    # To run it yourself, copy the below line and:
    # 1. Fill in $SERVICE for the docker service you want to test
    # 2. (Optional) Remove -T for a prettier result
    # 3. (Optional) Remove everything starting from ; at the end
    docker-compose -f docker-compose-dev.yml exec -T $SERVICE bash -c 'PYTHONPATH=/app:$PYTHONPATH pytest /tests/*.py  --asyncio-mode=strict'; (( FAILURE=$FAILURE | $? ))
    echo Finished with failure code $FAILURE
    echo
done

# Run integration tests
# docker-compose -f docker-compose-dev.yml exec api-server bash -c 'PYTHONPATH=/app:$PYTHONPATH pytest /test/integration-*.py'; (( FAILURE=$FAILURE | $? ))
# docker-compose -f docker-compose-dev.yml exec worker1 bash -c 'PYTHONPATH=/app:$PYTHONPATH pytest /test/integration-*.py'; (( FAILURE=$FAILURE | $? ))

# Clean up after ourselves
# We only want to take the services down if we started them ourselves
echo "Cleaning up"
if [[ ! $RUNNING ]]
then docker-compose -f docker-compose-dev.yml down -v --remove-orphans
fi

# Exit with an exit code if any test failed
echo "Done"
# TO DO: We'll need to examine how to accept warnings perhaps
exit $FAILURE
