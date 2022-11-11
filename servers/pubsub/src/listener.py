import os, json, argparse, requests
from datetime import datetime
from google.cloud import storage
from google.cloud import pubsub_v1
from main import PubSubProcess
from pydantic import BaseModel
from typing import Dict
import time


from celery import Celery, Signature
from celery.utils.log import get_task_logger

# Define celery requirements
celery_app = Celery(
    "app", backend=os.getenv("CELERY_BACKEND_URL"), broker=os.getenv("CELERY_BROKER_URL")
)
logger = get_task_logger("main")

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
celery_app.autodiscover_tasks()


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


# Callback function for pubsub_listener
def download_from_message(message: pubsub_v1.subscriber.message.Message) -> None:
    """Callback function for pubsub_listener

    Parameters
    ----------
    message : subscriber_pull_message object
        google object for pull messages of pubsub from subscription
    """

    # Decode message so it can be serialised!
    if isinstance(message.data, bytes):
        message_data = message.data.decode("utf-8")
    else:
        message_data = message.data

    # Print messages
    print(f"Received {message}.")
    print(f"Data: {message_data}")

    # Create message dict
    message_dict = {}
    message_dict["message_id"] = message.message_id
    message_dict["data"] = message_data
    message_dict["attributes"] = dict(message.attributes)

    bucket_name = message_dict["attributes"]["bucketId"]

    try:
        if not ("date_str" in message_dict["attributes"]):
            raise Exception(f"InputError: Could not find date_str in input attributes.")
        if not ("basepath" in message_dict["attributes"]):
            raise Exception(f"InputError: Could not find basepath in input attributes.")

        base_path = message_dict["attributes"]["basepath"]
        date_str = message_dict["attributes"]["date_str"]
        time_str = message_dict["attributes"]["time_str"]
        metadata = message_dict["attributes"]["metadata"]
        cleanup_pipeline = message_dict["attributes"]["cleanup_pipeline"]
        upload_letsgrow = message_dict["attributes"]["upload_letsgrow"]

        message_dict_serialised = json.dumps(message_dict)
        metadata = message_dict

        output_path = str(os.getenv("PIPELINE_OUTPUT_FOLDER"))
        data_output_dir = os.path.join(output_path, "0.rawfile")
        error_log_output_dir = os.path.join(output_path, "errors")
        os.makedirs(error_log_output_dir, exist_ok=True)
        os.makedirs(data_output_dir, exist_ok=True)

        # Check if filename ends with zip
        if os.path.splitext(base_path)[1] == ".zip":

            output_filepath = os.path.join(data_output_dir, base_path)

            storage_client = storage.Client()
            blob = storage_client.bucket(bucket_name).get_blob(base_path)
            blob.download_to_filename(output_filepath)

            if os.path.isfile(output_filepath):

                # set up pipeline endpoints to post
                api_server_port = 80
                api_method = "start-flex-pipeline-all-frames"
                url = f"http://api-server:{api_server_port}/{api_method}"

                body = StartPipelineBody(
                    zip_filepath=output_filepath,
                    metadata=metadata,
                    cleanup_pipeline=cleanup_pipeline,
                    upload_letsgrow=upload_letsgrow,
                )

                print("DEBUG: Sending post request...")
                r = requests.post(url, json=body.__dict__)

            else:
                print(f"Error encountered while saving this file: {output_filepath}")

    except Exception as e:
        print(f"ERROR in callback: Error downloading paths!! Exception - {e}")
        message.nack()

    # Acknowledge the message. Unack'ed messages will be redelivered.
    message.ack()
    print(f"Acknowledged {message.message_id}.")


def main(
    project_name: str = "sobolt-plantfellow",
    subscriber: str = "flex-dev-sub",
    bucket_name: str = "pf-flex-pipeline-test",
):
    """
    main function to run the listener

    Parameters
    ----------
    project_name : str, optional
        GCP project name, by default "sobolt-plantfellow"
    subscriber : str, optional
        GCP PUBSUB subscriber name, by default "flex-dev-sub"
    bucket_name : str, optional
        GCP bucket name, by default "pf-flex-pipeline-test"
    """

    # listen for each file
    try:
        datetimes = datetime.now().strftime("%Y-%m-%d_%H-%M")
        acquisition_date = datetimes.split("_")[0]
        acquisition_time = datetimes.split("_")[1]
        metadata = {"test": "rc_visard flex tomato data"}
        PS = PubSubProcess(
            acquisition_date,
            acquisition_time,
            f"test",
            metadata,
            subscribe_to=subscriber,
            project=project_name,
            bucket_name=bucket_name,
        )
        PS.acknowledge_messages(download_from_message)
    except:
        print(f"No messages found... trying again")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Publish message(s) if new file(s) have been uploaded bucket which will initiate the analysis pipeline"
    )
    # Required arguments
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
        help="Bucket name (e.g. 'pf-flex-pipeline-test').",
    )
    parser.add_argument(
        "--subscriber",
        "-tp",
        metavar="STR",
        type=str,
        default="flex-dev-sub",
        help="Subscriber to listen to (for example: flex-dev-sub)",
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
    if str(os.getenv("GCP_SUBSCRIPTION")):
        subscriber = str(os.getenv("GCP_SUBSCRIPTION"))
    else:
        subscriber = args.subscriber
    while True:
        main(project, subscriber, bucket)
        time.sleep(120)
