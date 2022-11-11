Plantfellow Flex cloud pipeline
========================
This is repository contains all the relevant code for the cloud pipeline.
The pipeline automatically checks for any new data uploaded to the Flex production bucket, dowloads them, analyse and upload to the LetsGrow platform. The pipeline codes includes the main modules like the VM manager, pipeline handler, the API server, but it also has implementation of measurement modules.

## Dependencies

* [Docker](https://www.docker.com/). You can find instructions for [installing docker on ubuntu here](https://docs.docker.com/engine/install/ubuntu/)
* [Docker compose 1.29.2](https://docs.docker.com/compose/). You can find [installation instructions here](https://docs.docker.com/compose/install/)

## Virtual machines (orchestrator and workers)

* GCP Service account: A service account to manage all the worker VMs. It should have all the `Compute Instance Admin (beta)` and `Storage Object` roles. The service account credentials can be generated with key `json` file. The path to this file can be defined in the environment file (follow the template present in the repository).
* Orchestrator VM: This VM runs the pipeline present in this codebase, spawns the worker VMs, deploys the docker containers on them, and at the end removes the once the workers are no longer needed. This VM needs to have `full access to all the cloud APIs`.
* Disk CPU image: A template to create the worker VMs to run all the CPU dependent processes, i.e. pipeline manager, downloading, preprocessing, measurements. A segmentation worker can also be spawned with this template, with the caveat the segmenation module will run on CPU instead of the preferred GPU based worker.
* Disk GPU image (optional): A template to create the worker VMs for the segmentation module (Note: edit the VM configuration file if you opt out of creating this disk)



## How to use

To run in development mode on a single VM;

1. Login to a VM instance with the all the above accesses.
2. Clone the pipeline repo.
3. Change the paths of  service account json file and output folder in the template env file.
4. Copy the updated env file to a file named `.env`.
5. Copy the empty archive json file from the repo to the output folder. The publisher will read this file to compare files with the bucket.
6. Build and bring the pipeline up:
```
docker-compose -f docker-compose-dev.yml --profile local_dev up --build
```
Bring the pipeline down with:
```
docker-compose -f docker-compose-dev.yml --profile local_dev down --remove-orphans
```

To run in development mode and deploy worker VMs, Login to the orchestrator VM.


Build and bring the pipeline up with:
```
docker-compose -f docker-compose-dev.yml --profile external_dev up --build
```

Bring the pipeline down with:
```
docker-compose -f docker-compose-dev.yml --profile external_dev down --remove-orphans
```

#### Run measuring as a standalone process

The measurements can be obtained for a las file, by building and docker image and running it as follows:
```
# from root
docker build -f ./workers/measuring/Dockerfile.dev -t measuring_dev .
docker run --rm -it -v /PATH/TO/DATA:/data -v ./workers/measuring/src:/app measuring_dev:latest python main.py -i /PATH/TO/FILE -o /PATH/TO/OUTPUT_FOLDER
```

#### Run preprocessing as a standalone process

The preprocessesing can be obtained for a raw zip file, by building and docker image and running it as follows:
```
# from root
docker build -f ./workers/preprocessing/Dockerfile.dev -t preprocessing_dev .
docker run --rm -it -v /PATH/TO/DATA:/data -v ./workers/preprocessing/src:/app preprocessing_dev:latest python preprocess.py -i /PATH/TO/ZIPFILE -o /PATH/TO/OUTPUT_FOLDER
```

#### Run segmentation as a standalone process (Needs GPU)

The segmentation can be obtained for a las file, by building and docker image and running it as follows (NEEDS GPU):
```
# from root
docker build -f ./workers/segmenation/Dockerfile -t segmentation_dev .
docker run --rm -it -v /PATH/TO/DATA:/data -v ./workers/measuring/src:/app segmentation_dev:latest python predict.py -i /PATH/TO/LASFILE -o /PATH/TO/OUTPUT_LAS
```

### Documentation

Further documentation on how to work with the pipeline can be found [here](https://docs.google.com/document/d/1Re0dGqcsonACaYdlqPIVD8nJXwyPItFj8vkeydV6I5s/edit#)

### Repository structure
```
📦plantfellow.flex.pipeline
 ┣ 📂classes                              ---> classes folder with database and config class
 ┣ 📂servers                              ---> Pipeline API, VM manager, pubsub managers
 ┃ ┣ 📂api-server                         ---> API server with Celery backend to orchestrate the pipeline
 ┃ ┣ 📂pubsub                             ---> PubSub manager. Contains: the main class,
 ┃ ┃                                               listener for subcribing to messages and initiating the pipeline
 ┃ ┃                                               publisher for checking bucket for new files and publish messages for them
 ┃ ┗ 📂vm-manager                         ---> VM manager for spawning worker VMs. Contains:
 ┃ ┃                                               main class, VM configurations for the worker VMs
 ┃ ┃                                               Manage classes VM class to spawn, start and stop VMs
 ┃ ┃                                               Shutdown & start up scripts for the CPU and GPU workers
 ┣ 📂workers
 ┃ ┣ 📂segmentation                       ---> Segmentation process. Main code is in the docker image. This folder contains:
 ┃ ┃                                               Worker script to run the segmentation celery worker
 ┃ ┣ 📂measuring                          ---> Measuring process. Contains:
 ┃ ┃                                               Main class for measurements,
 ┃ ┃                                               Worker script to run the measuring celery worker
 ┃ ┣ 📂pipeline-manager                   ---> Pipeline manager with celery backend. Contains:
 ┃ ┃                                               Main class and worker
 ┃ ┗ 📂preprocessing                      ---> Preprocessing process. Contains:
 ┃ ┃                                               Main class for preprocessing
 ┃ ┃                                               Worker script for preprocessing
 ┣ 📜archive_files.json                   ---> Template archive json file: should contain a list of processed files
 ┣ 📜bitbucket-pipelines.yml
 ┣ 📜docker-compose-build.yml
 ┣ 📜docker-compose-dev.yml
 ┣ 📜docker-compose.yml
 ┗ 📜template_env.env                     ---> Template environment file
```
## Contributing

Contributing is as simple as installing using the instructions above and pushing
changes. Please do follow the following recommendations:

* Follow Sobolt's [Git workflow](https://docs.google.com/document/d/1thNfVOkyvZ9EnM6t23NA3gVOyOkDqdtZval7b0lg-5I) (also have a look at [this slidedeck](https://docs.google.com/presentation/d/1Pp4rMVUPEHGI0I1RFThIrnxUy_vnK3rRApbKyXrIPfI/edit#slide=id.g61a2fcb797_0_221))
* Before committing any changes, even on a branch, install and register pre-commit with the following command from the repository root: `pip install --user pre-commit; pre-commit install`
* Follow the coding style
* Document code using Markdown docstrings

## Version
The following changes have been implemented as a result of repository version update:

### 09-2022: 0.1.0

* Setup of the repository
* First version of the measuring worker
* First version of the pipeline

### 11-2022: 0.6.0

* First candidate pipeline
