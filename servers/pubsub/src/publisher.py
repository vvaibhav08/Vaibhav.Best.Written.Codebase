import os, json, argparse
from google.cloud import storage
from main import PubSubProcess
from typing import List, Dict, Tuple, Any
import time


def check_new_uploads(
    archive_file: str,
    project_name: str = "sobolt-plantfellow",
    bucket_name: str = "pf-flex-pipeline-test",
) -> Tuple[Any, Any]:
    """
    check_new_uploads
    Check the bucket for newly uploaded files, by comparing it
    with a locally saved list of files that have already been processed
    with the pipeline in the past.

    Parameters
    ----------
    archive_file : str
        Archive json file containing the list of processed files
    project_name : str, optional
        GCP project name, by default "sobolt-plantfellow"
    bucket_name : str, optional
        GCP bucket name, by default "pf-flex-pipeline-test"

    Returns
    -------
    Tuple[Any, Any]
        New set of files, Total list of files (to update the archive)
    """
    client = storage.Client(project_name)
    bucket = client.get_bucket(bucket_name)
    blobs = bucket.list_blobs()

    file_list = [blob.name for blob in blobs]

    # compare this list with the old list
    ## read the archive file list
    with open(archive_file) as f:
        filelist = json.load(f)

    old_list = filelist["old_list"]

    # get difference
    new_files = get_list_differences(file_list, old_list)

    return new_files, file_list


def get_list_differences(list1: List, list2: List) -> List:
    """
    get_list_differences
    Get the difference between 2 filelist

    Parameters
    ----------
    list1 : list
        First file list
    list2 : list
        Second file lisy

    Returns
    -------
    list
        List of files that are in one list but not in the other
    """
    difference = set(list1) ^ set(list2)
    return list(difference)


def get_file_metadata(filepath: str) -> Dict:
    """
    get_file_metadata
    Parses the filename and in order to extract all required information for the upload

    Parameters
    ----------
    filepath : str
        input zip file

    Returns
    -------
    Dict
        metadata
    """
    metadata = {
        "filetype": None,
        "visardid": None,
        "timestamp": None,
        "plantpath": None,
        "plantid": None,
        "fileinfo": None,
    }
    try:
        # Get file type:
        filename = os.path.basename(filepath).split(".")[0]
        filename_split = filename.split("_")
        # Get the serial number of the rc_visard
        if "rc-visard" in filename_split:
            rc_idx = filename_split.index("rc-visard")
            rc_visard_id = filename_split[rc_idx + 1]

        # Extract the timestamp
        timestamp = f"{filename_split[2]}T{filename_split[3].replace('-', ':')}"

        # Get the file type, options: [Kop, Blad, Tros]
        if "kop" in filename.lower():
            file_type = "kop"
        elif "blad" in filename.lower():
            file_type = "blad"
        elif "tros" in filename.lower():
            file_type = "tros"
        else:
            file_type = "unknown"

        # get plant id
        if "pad" in filename_split:
            path_idx = filename_split.index("pad")
            path_number = filename_split[path_idx + 1]

        # get plant number
        if "plant" in filename_split:
            plant_idx = filename_split.index("plant")
            plant_number = filename_split[plant_idx + 1]

        metadata["filetype"] = file_type  # type: ignore
        metadata["visardid"] = rc_visard_id  # type: ignore
        metadata["timestamp"] = timestamp  # type: ignore
        metadata["pathid"] = path_number  # type: ignore
        metadata["plantid"] = plant_number  # type: ignore
        metadata["fileinfo"] = f"Plant-{plant_number} {file_type}-datafile-{filename}"  # type: ignore
    except Exception as e:
        print(f"Could not parse filename: {e}")

    return metadata


def main(
    archive_file: str,
    project_name: str = "sobolt-plantfellow",
    topic: str = "flex-dev",
    bucket_name: str = "pf-flex-pipeline-test",
):
    """
    main function to publish the messages for each class

    Parameters
    ----------
    archive_file : str
        Archive file containing a list of files already processed through the pipeline
    project_name : str, optional
        GCP project name, by default "sobolt-plantfellow"
    topic : str, optional
        GCP PUBSUB Topic name, by default "flex-dev"
    bucket_name : str, optional
        GCP bucket name, by default "pf-flex-pipeline-test"
    """
    # new files
    files_to_process, updated_list = check_new_uploads(
        archive_file, project_name, bucket_name
    )
    cleanup_pipeline = os.getenv("CLEANUP", "False").lower() == "true"
    upload_letsgrow = os.getenv("UPLOAD_LETSGROW", "False").lower() == "true"

    if len(files_to_process) > 0:
        # publish for each file
        for filename in files_to_process:
            acquisition_date = filename.split(".")[0].split("_")[2]
            acquisition_time = filename.split(".")[0].split("_")[3]
            metadata = get_file_metadata(filename)

            PS = PubSubProcess(
                acquisition_date,
                acquisition_time,
                f"{filename}",
                metadata,
                cleanup_pipeline=cleanup_pipeline,
                upload_letsgrow=upload_letsgrow,
                publish_to=topic,
                project=project_name,
                bucket_name=bucket_name,
            )
            PS.publish_message_to_topic()

        # update the old file list
        up_list = {"old_list": updated_list}
        with open(archive_file, "w") as f:
            json.dump(up_list, f)
    else:
        print(f"No new files are present in the bucket.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Publish message(s) if new file(s) have been uploaded bucket which will initiate the analysis pipeline"
    )
    # Required arguments
    parser.add_argument(
        "--archivefile",
        "-ar",
        metavar="PATH",
        type=str,
        default="/data/archive_files.json",
        help="Path to the archive file where old file list is present (ex: archive_files.json)",
    )
    parser.add_argument(
        "--project",
        "-p",
        metavar="STR",
        type=str,
        default="sobolt-plantfellow",
        help="Bucket name (e.g. 'sobolt-plantfellow').",
    )
    parser.add_argument(
        "--bucket",
        "-b",
        metavar="STR",
        type=str,
        default="pf-flex-pipeline-test",
        help="Bucket name (e.g. 'flex-bucket-test').",
    )
    parser.add_argument(
        "--topic",
        "-tp",
        metavar="STR",
        type=str,
        default="flex-dev",
        help="Topic to publish to (for example: flex-dev)",
    )
    # Optional arguments
    parser.add_argument(
        "--sleep-time",
        "-st",
        metavar="INT",
        type=int,
        default=1,
        help="Number of minutes to wait/sleep in between every published message (defaults to 1).",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Turn verbose mode on"
    )
    args = parser.parse_args()

    if str(os.getenv("GCP_BUCKET")):
        bucket = str(os.getenv("GCP_BUCKET"))
    else:
        bucket = args.bucket
    if str(os.getenv("GC_PROJECT")):
        project = str(os.getenv("GC_PROJECT"))
    else:
        project = args.project
    if str(os.getenv("GCP_TOPIC")):
        topic = str(os.getenv("GCP_TOPIC"))
    else:
        topic = args.topic
    if str(os.getenv("ARCHIVE_JSON")):
        archivefile = str(os.getenv("ARCHIVE_JSON"))
    else:
        archivefile = os.path.join(
            str(os.getenv("PIPELINE_OUTPUT_FOLDER")), os.path.basename(args.archivefile)
        )

    if str(os.getenv("GCP_BUCKET")):
        bucket = str(os.getenv("GCP_BUCKET"))
    else:
        bucket = args.bucket
    if str(os.getenv("GC_PROJECT")):
        project = str(os.getenv("GC_PROJECT"))
    else:
        project = args.project
    if str(os.getenv("GCP_TOPIC")):
        topic = str(os.getenv("GCP_TOPIC"))
    else:
        topic = args.topic
    if str(os.getenv("ARCHIVE_JSON")):
        archivefile = str(os.getenv("ARCHIVE_JSON"))
    else:
        archivefile = os.path.join(
            str(os.getenv("PIPELINE_OUTPUT_FOLDER")), os.path.basename(args.archivefile)
        )

    print(os.listdir(str(os.getenv("PIPELINE_OUTPUT_FOLDER"))))
    print("archivefile")
    print(archivefile)
    # Only check archive when also uploading files
    assert os.path.isfile(archivefile), f"Could not find '{archivefile}'"
    while True:
        main(archivefile, project, topic, bucket)
        time.sleep(120)
