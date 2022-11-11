import os, traceback
from os.path import join, basename, exists
import pandas as pd
from typing import Dict, List, Tuple
from celery import Celery
from celery.utils.log import get_task_logger

from preprocess import Preprocessor

# Check if required environment variables are set
assert os.getenv("CELERY_BACKEND_URL") is not None
assert os.getenv("CELERY_BACKEND_URL") != ""
assert os.getenv("CELERY_BROKER_URL") is not None
assert os.getenv("CELERY_BROKER_URL") != ""
assert os.getenv("PIPELINE_OUTPUT_FOLDER") is not None
assert os.getenv("PIPELINE_OUTPUT_FOLDER") != ""

# Create the celery app and get the logger
app = Celery(
    "app",
    backend=os.getenv("CELERY_BACKEND_URL"),
    broker=os.getenv("CELERY_BROKER_URL"),
)
logger = get_task_logger(__name__)

app.conf.update(
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


@app.task(name="tasks.preprocess", serializer="json")
def preprocess(task_info: Dict) -> Dict:
    """
    preprocess worker
    Preprocess the best frame from a raw zip rc_visard file to obtain a
    las file. Takes in a task_info dictionary containing file to process,
    and some meta. Run the preprocess process and updates the task_info
    with output file

    Parameters
    ----------
    task_info : Dict
        Task dictionary. This contains the file path, and metadata

    Returns
    -------
    Dict
        Task dictionary, updated with the filepath replaced with the output.
    """
    new_task_info = task_info.copy()

    # Fetch raw files from task_info
    zip_file_paths = [f for f in task_info["files"] if f["source"] == "ZIPRAW"]
    assert (
        len(zip_file_paths) > 0
    ), f"Something went wrong, no file with source 'ZIPRAW' found in task_info object!\n{task_info}"
    input_zip_file_path = zip_file_paths[0]["path"]

    output_folder_path = str(os.getenv("PIPELINE_OUTPUT_FOLDER"))
    data_output_dir = join(output_folder_path, "1.preprocessed")
    os.makedirs(data_output_dir, exist_ok=True)

    # Prepare error log folder + path
    error_log_dir = join(output_folder_path, "errors")
    os.makedirs(error_log_dir, exist_ok=True)
    error_log_path = join(
        error_log_dir, f"1.preprocessing_{basename(input_zip_file_path)}_error.txt"
    )

    if not input_zip_file_path:
        print(f"Something went wrong and we could not find the input zip file...")

    try:
        pre = Preprocessor(
            input_zip_file_path,
            data_output_dir,
            filter_noise=True,
            debug=True,
            silent=False,
        )

        ply_path = pre.create_best_pointcloud()
        las_path = pre.ply_to_las([ply_path])[0]

        new_task_info["files"].append({"path": las_path, "source": "PREPROCESS"})

        return new_task_info
    except Exception as e:
        error_message = traceback.format_exc()
        with open(error_log_path, "w") as f:
            f.write(error_message)
        print(error_message)

        return new_task_info


@app.task(name="tasks.preprocess_all_frames", serializer="json")
def preprocess_all_frames(task_info: Dict) -> Dict:
    """Preprocess all suitable frames from the
    rc-visard recording.

    Parameters
    ----------
    task_info : Dict
        Task dictionary. This contains the file path, and metadata

    Returns
    -------
    Dict
        Task dictionary, updated with the filepath replaced with the output.
    """
    new_task_info = task_info.copy()

    # Fetch raw files from task_info
    zip_file_paths = [f for f in task_info["files"] if f["source"] == "ZIPRAW"]
    assert (
        len(zip_file_paths) > 0
    ), f"Something went wrong, no file with source 'ZIPRAW' found in task_info object!\n{task_info}"
    input_zip_file_path = zip_file_paths[0]["path"]

    output_folder_path = str(os.getenv("PIPELINE_OUTPUT_FOLDER"))
    data_output_dir = join(output_folder_path, "1.preprocessed")
    os.makedirs(data_output_dir, exist_ok=True)

    # Fetch settings from task_info
    metadata = task_info["settings"]["metadata"]
    overwrite = task_info["settings"]["overwrite"]
    debug = task_info["settings"]["debug"]

    # Prepare error log folder + path
    error_log_dir = join(output_folder_path, "errors")
    os.makedirs(error_log_dir, exist_ok=True)
    error_log_path = join(
        error_log_dir, f"1.preprocessing_{basename(input_zip_file_path)}_error.txt"
    )

    if not input_zip_file_path:
        print(f"Something went wrong and we could not find the input zip file...")

    try:
        pre = Preprocessor(
            input_zip_file_path,
            data_output_dir,
            filter_noise=True,
            debug=True,
            silent=False,
            overwrite=overwrite,
        )

        ply_paths = pre.create_pointclouds(select_suitable=False)
        las_paths = pre.ply_to_las(ply_paths)
        assert (
            len(las_paths) > 0
        ), f"No preprocessed .las files for this rc-visard recording! {input_zip_file_path}"

        for las_path in las_paths:
            new_task_info["files"].append({"path": las_path, "source": "PREPROCESS"})

        return new_task_info
    except Exception as e:
        error_message = traceback.format_exc()
        with open(error_log_path, "w") as f:
            f.write(error_message)
        print(error_message)

        return new_task_info
