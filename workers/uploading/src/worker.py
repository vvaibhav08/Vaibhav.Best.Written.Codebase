import os, traceback
from os.path import join, basename, exists
import pandas as pd
from typing import Dict, List, Tuple
from celery import Celery
from celery.utils.log import get_task_logger

from upload import Uploader
from letsgrow_helper import LetsGrowHelper

# Check if required environment variables are set
assert os.getenv("CELERY_BACKEND_URL") is not None
assert os.getenv("CELERY_BACKEND_URL") != ""
assert os.getenv("CELERY_BROKER_URL") is not None
assert os.getenv("CELERY_BROKER_URL") != ""

# Check if required username & password are set
assert os.getenv("LETSGROW_API_USERNAME") is not None
assert os.getenv("LETSGROW_API_USERNAME") != ""
assert os.getenv("LETSGROW_API_PASSWORD") is not None
assert os.getenv("LETSGROW_API_PASSWORD") != ""

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


@app.task(name="tasks.upload", serializer="json")
def upload(task_info: Dict):
    """
    upload worker
    Uploads the results from the .csv to the LetsGrow API

    Parameters
    ----------
    task_info : Dict
        Task dictionary. This contains the file path, and metadata

    """
    new_task_info = task_info.copy()

    # Fetch raw files from task_info
    results_file_paths = [
        f for f in task_info["files"] if f["source"] == "MEASUREMENT_CSV"
    ]
    assert (
        len(results_file_paths) > 0
    ), f"Something went wrong, no file with source 'MEASUREMENT_CSV' found in task_info object!\n{task_info}"
    results_file_path = results_file_paths[0]["path"]

    if task_info["settings"]["upload_letsgrow"]:
        if not results_file_path:
            print(f"Something went wrong and we could not find the input .csv file...")

        try:

            # Init helper
            lg = LetsGrowHelper()

            # Login to API
            lg.login()
            print(f"Connected to API: {lg.connected}")
            print(lg.connected)

            if lg.connected:
                # Iniitalize uploader
                uploader = Uploader(results_file_path, lg)

                # Upload values from .csv
                values = uploader.load_values()
                uploader.upload(values)
            else:
                # TODO: put in LetsGrow upload cue, periodically check if LetsGrow is available
                print("Could not log in to LetsGrow")

            return new_task_info

        except Exception as e:
            error_message = traceback.format_exc()
            # with open(error_log_path, "w") as f:
            #    f.write(error_message)
            print(error_message)

            return new_task_info
    else:
        print(f"Not uploading to LetsGrow since it is set to False!")
        return new_task_info
