import os
from os.path import join, basename, splitext, split, exists
import time
from copy import deepcopy
from os.path import basename, join, splitext, exists, isdir
from typing import Union, Dict
import traceback
from typing import Dict, Any, Tuple, Union, List, Type, Optional
from celery import Celery, Signature, chain, subtask, group, chord
from celery.utils.log import get_task_logger
import shutil

# Create the celery app and get the logger
app = Celery(
    "app", backend=os.getenv("CELERY_BACKEND_URL"), broker=os.getenv("CELERY_BROKER_URL")
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


@app.task(name="tasks.cleanup", serializer="json")
def cleanup(task_info: Dict, skipping: List[str] = []) -> Dict:
    """
    cleanup
    Clean up of intermediate files produced during the pipeline run
    Takes in  a task_info dictionary containing file to process,
    and some meta. Run the cleanup process and updates the task_info
    with output file

    Parameters
    ----------
    task_info : Dict
        Task dictionary. This contains the file path, and metadata
    skipping : List[str], optional
        Source of files to skip. Skipped files won't be removed, by default []

    Returns
    -------
    Dict
        Task dictionary, updated with the filepath replaced with the output.
    """
    logger.info("start cleanup")

    new_task_info = task_info.copy()
    new_task_info["files"] = []

    for f in task_info["files"]:
        if task_info["settings"]["cleanup_datastorage"]:
            if f["source"] in skipping:
                continue
            elif exists(f["path"]):
                if isdir(f["path"]):
                    shutil.rmtree(f["path"])
                else:
                    os.remove(f["path"])
        else:
            if f["path"] not in new_task_info["files"]:
                new_task_info["files"].append(f)

    return new_task_info


@app.task(name="tasks.dmap", serializer="json")
def dmap_src(task_info: Dict, celery_task: Any, split_source: str) -> Any:
    """Split pipeline per source and merge results after.

    For example: Run segmentation and measuring on every
    preprocessed file from the rc-visard recording.
    Preprocessed files are recognized by the 'PREPROCESS'
    source.

    Parameters
    ----------
    task_info : Dict
        Taks info object containing one or multiple
        files with the source to split on.
    celery_task : Any
        Celery task to run on every file with source
    split_source : str
        File source to run a certain celery task on.

    Returns
    -------
    Any
        The resulting celery task
    """
    source_files = [f for f in task_info["files"] if f["source"] == split_source]
    job_infos = []
    for sf in source_files:
        j = task_info.copy()
        j["files"] = [f for f in j["files"] if f["source"] != split_source]
        j["files"].append(sf)
        job_infos.append(j)

    if len(job_infos) == 0:
        job_infos = [task_info.copy()]

    callback = subtask(celery_task)
    run_in_parallel = chord(
        group(clone_signature(callback, args) for args in job_infos),
        Signature("tasks.merge_taskinfo", queue="pipeline-manager"),
    )
    job_result = run_in_parallel.apply_async()
    results = job_result.get(disable_sync_subtasks=False)

    return results


@app.task(name="tasks.merge_taskinfo", serializer="json")
def merge_taskinfo(jobs: List[Dict]) -> Dict:
    """Merge task info objects into a singel task
    info object.

    Parameters
    ----------
    jobs : List[Dict]
        List of task info objects

    Returns
    -------
    Dict
        Merged task info dictionary
    """
    logger.info("start merge")
    if isinstance(jobs[0], list):
        jobs = jobs[0]

    job_info = jobs[0]

    for i in range(1, len(jobs)):
        file_paths = [f["path"] for f in job_info["files"]]

        for f in jobs[i]["files"]:
            if f["path"] not in file_paths:
                job_info["files"].append(f)
    return job_info


def clone_signature(sig, args=(), kwargs=(), **opts):
    """
    Turns out that a chain clone() does not copy the arguments properly - this
    clone does.
    From: https://stackoverflow.com/a/53442344/3189
    """
    args = [args]

    if sig.subtask_type and sig.subtask_type != "chain":
        raise NotImplementedError(
            "Cloning only supported for Tasks and chains, not {}".format(sig.subtask_type)
        )
    clone = sig.clone()
    if hasattr(clone, "tasks"):
        task_to_apply_args_to = clone.tasks[0]
    else:
        task_to_apply_args_to = clone
    args, kwargs, opts = task_to_apply_args_to._merge(
        args=args, kwargs=kwargs, options=opts
    )
    task_to_apply_args_to.update(args=args, kwargs=kwargs, options=deepcopy(opts))
    return clone
