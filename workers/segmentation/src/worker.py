import os
import os.path
from os.path import join, basename, splitext, split, exists
import traceback
from datetime import datetime
from typing import Any, Dict, List, Tuple, Type, Union

from celery import Celery
from celery.utils.log import get_task_logger

from predict import main
from classes.config import PipelineFolderStructure
from segment import Segment

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


@app.task(name="tasks.segment", serializer="json")
def segmentation_predict(task_info: Dict) -> Dict:
    """Convert rcvisard data to a single .laz file.

    Parameters
    ----------
    task_info : Dict
        Dictionary with information about the file and
        parameters of the run.

    Returns
    -------
    Dict
        Output task_info including the new segmented data.
    """
    new_task_info = task_info.copy()

    # Fetch preprocessed files from task_info
    preprocessed_paths = [f for f in task_info["files"] if f["source"] == "PREPROCESS"]
    assert (
        len(preprocessed_paths) > 0
    ), f"Something went wrong, no file with source 'PREPROCESS' found in task_info object!\n{task_info}"
    raw_las = preprocessed_paths[0]["path"]

    # Fetch settings from task_info
    metadata = task_info["settings"]["metadata"]
    overwrite_option = task_info["settings"]["overwrite"]
    debug = task_info["settings"]["debug"]

    # Prepare output folder
    output_folder = str(os.getenv("PIPELINE_OUTPUT_FOLDER"))

    FS = PipelineFolderStructure(output_folder)
    data_output_dir = FS.SEGMENTATION_DIR
    error_log_output_dir = FS.ERROR_LOG_DIR
    # os.makedirs(error_log_output_dir, exist_ok=True)
    os.makedirs(data_output_dir, exist_ok=True)
    # Prepare error log folder + path
    error_log_dir = join(output_folder, "errors")
    error_log_path = join(error_log_dir, f"1.segmentation_{basename(raw_las)}_error.txt")

    raw_las_name = basename(raw_las).split(".")[0]
    output_path = join(data_output_dir, f"{raw_las_name}_segmented.las")

    try:
        # Don't create output file if already exists
        if not overwrite_option and exists(output_path):
            print(f"returning: {new_task_info}")
            new_task_info["files"].append({"path": output_path, "source": "SEGMENTATION"})
            return new_task_info

        main(raw_las, output_path, model_type="multi")
        assert exists(output_path), f"ERROR: Output file of segmented data "

        # Translate segmented point cloud to original center
        s = Segment(debug=debug, silent=False)
        s.translate_segmentation_to_original_center(raw_las, output_path)

        new_task_info["files"].append({"path": output_path, "source": "SEGMENTATION"})

        print(f"returning: {new_task_info}")
        return new_task_info
    except Exception as e:
        error_message = traceback.format_exc()
        with open(error_log_path, "w") as f:
            f.write(error_message)
        print(error_message)

        return new_task_info
