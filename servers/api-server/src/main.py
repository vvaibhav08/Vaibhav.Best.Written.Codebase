import os
import uuid

from celery import Celery, Signature, chain, chord, group
from celery.execute import send_task
from celery.utils.log import get_task_logger
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List


# Create the FastAPI app
app = FastAPI()

# Define celery requirements
celery_app = Celery(
    "app", backend=os.getenv("CELERY_BACKEND_URL"), broker=os.getenv("CELERY_BROKER_URL")
)
logger = get_task_logger(__name__)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json", "application/json"],
    task_acks_late=True,
    task_time_limit=604800,
    broker_transport_options={
        "visibility_timeout": 604800,
        "max_retries": 0,
        "ack_emulation": False,
    },
)

logger.info("API server entered + initialised!")
logger.info(f"{__name__}")
logger.info(f"{type(__name__)}")
logger.info(logger)


@app.get("/")
def index():
    logger.info('index("/"): \tCurrently at index!')
    return {"Hello": "World"}


@app.post("/start-pipeline-message")
def start_pipeline_message(filename: str):
    logger.info("Received start-pipeline request!")
    logger.info(f"Inputs: {filename}")
    return {"message": "Start pipeline successful!", "inputs": f"{filename}"}


@app.post("/pipeline-test-preprocessing")
def pipeline_preprocess(filepath: str):
    """
    pipeline_preprocess task api endpoint

    Parameters
    ----------
    filepath : str
        zip file path to process

    Returns
    -------
    _type_
        task id
    """
    # Create group of task signatures for preprocessing and execute
    metadata = {"preprocessing test": "preprocessing test"}
    task_input = prepare_task_input(filepath, metadata)
    r = Signature("tasks.preprocess", args=[task_input], queue="preprocessing")
    r.apply_async()

    logger.info(
        f"pipeline-test-preprocessing FINISHED! Execution successful - Results {r.get()}"
    )
    return r.id


@app.post("/pipeline-test-segmentation")
def pipeline_segment(preprocessed_input: str):
    """
    pipeline_segment task api endpoint

    Parameters
    ----------
    preprocessed_input : str
        preprocessed las file

    Returns
    -------
    _type_
        task id
    """
    # Create callback task for the box segmentation step and execute
    metadata = {"segmentation test": "segmentation test"}
    task_input = prepare_task_input(preprocessed_input, metadata)
    r = Signature("tasks.segment", args=[task_input], queue="segmentation")
    r.apply_async()

    logger.info(
        f"pipeline-test-segmentation FINISHED! Execution successful - Results {r.get()}"
    )
    return r.id


@app.post("/pipeline-test-measuring")
def pipeline_measure(segmented_input: str):
    """
    pipeline_measure task api endpoint

    Parameters
    ----------
    segmented_input : str
        segmented las file

    Returns
    -------
    _type_
        task id
    """
    # Create callback task for the box segmentation step and execute
    metadata = {"measure_test": "measure_test"}
    task_input = prepare_task_input(segmented_input, metadata)
    r = Signature("tasks.measure", args=[task_input], queue="measuring")
    r.apply_async()

    logger.info(
        f"pipeline-test-measuring FINISHED! Execution successful - Results {r.get()}"
    )
    return r.id


class StartPipelineBody(BaseModel):
    """
    StartPipelineBody - base class for input

    Parameters
    ----------
    BaseModel : base model
        base model
    """

    zip_filepath: str
    metadata: Dict
    cleanup_pipeline: bool
    upload_letsgrow: bool


@app.post("/start-flex-pipeline")
def start_pipeline(body: StartPipelineBody) -> str:
    """
    start_pipeline

    Parameters
    ----------
    body : StartPipelineBody
        pipeline body; contains zip file path and metadata

    Returns
    -------
    str
        confirmation that pipeline has started
    """
    zip_file = body.zip_filepath
    metadata = body.metadata
    attributes = metadata["attributes"]
    metadata = attributes
    cleanup = body.cleanup_pipeline
    upload_letsgrow = body.upload_letsgrow

    task_input = prepare_task_input(zip_file, metadata, cleanup, upload_letsgrow)
    r = chain(
        Signature("tasks.preprocess", args=[task_input], queue="preprocessing"),
        Signature("tasks.segment", queue="segmentation"),
        Signature("tasks.measure", queue="measuring"),
        Signature("tasks.upload", queue="uploading"),
        Signature(
            "tasks.cleanup",
            kwargs={"skipping": ["MEASUREMENT_CSV", "METADATA_CSV"]},
            queue="pipeline-manager",
        ),
    )
    r.apply_async()
    return "RUNNING"


def prepare_task_input(
    zip_file: str,
    metadata: Dict,
    cleanup_datastorage: bool = False,
    upload_letsgrow: bool = False,
) -> Dict:
    """
    prepare_task_input

    Parameters
    ----------
    zip_file : str
        raw zip file to be processed
    metadata : Dict
        metadata corresponding to the zip file
    cleanup_datastorage : bool
        choose whether to clean up afterwards, False by Default
    upload_letsgrow : bool
        choose whether to upload results to LetsGrow, False by Default

    Returns
    -------
    Dict
        task input as a dictionary
    """
    run_uuid = str(uuid.uuid4())

    task_files = [
        {"path": zip_file, "source": "ZIPRAW"},
    ]

    fileinfo = metadata["metadata"]
    filetype = metadata["file_type"]
    visard_id = metadata["visard_id"]
    plant_id = metadata["plant_id"]
    path_id = metadata["path_id"]
    task_input = {
        "settings": {
            "run_uuid": run_uuid,
            "overwrite": False,
            "debug": False,
            "metadata": fileinfo,
            "filetype": filetype,
            "visard_id": visard_id,
            "plant_id": plant_id,
            "path_id": path_id,
            "cleanup_datastorage": cleanup_datastorage,
            "upload_letsgrow": upload_letsgrow,
        },
        "files": task_files,
    }

    return task_input


@app.post("/start-flex-pipeline-all-frames")
def start_pipeline_all_frames(body: StartPipelineBody) -> str:
    """
    start_pipeline_all_frames

    Parameters
    ----------
    body : StartPipelineBody
        pipeline body; contains zip file path and metadata

    Returns
    -------
    str
        confirmation that pipeline has started
    """
    zip_file = body.zip_filepath
    metadata = body.metadata
    attributes = metadata["attributes"]
    metadata = attributes
    cleanup = body.cleanup_pipeline
    upload_letsgrow = body.upload_letsgrow

    task_input = prepare_task_input(zip_file, metadata, cleanup, upload_letsgrow)

    r = chain(
        Signature(
            "tasks.preprocess_all_frames", args=[task_input], queue="preprocessing"
        ),
        Signature(
            "tasks.dmap",
            kwargs={
                "split_source": "PREPROCESS",
                "celery_task": chain(
                    Signature("tasks.segment", queue="segmentation"),
                ),
            },
            queue="pipeline-manager",
        ),
        Signature("tasks.measure_multiple_frames", queue="measuring"),
        Signature("tasks.upload", queue="uploading"),
        Signature(
            "tasks.cleanup",
            kwargs={"skipping": ["MEASUREMENT_CSV", "METADATA_CSV"]},
            queue="pipeline-manager",
        ),
    )
    r.apply_async()
    return "RUNNING"
