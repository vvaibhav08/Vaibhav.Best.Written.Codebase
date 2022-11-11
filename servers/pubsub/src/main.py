import os, json
from datetime import datetime
from pytz import timezone  # type:ignore
from math import ceil  # for split_list_by_serialised_len function
from google.cloud import pubsub_v1, storage
from typing import List, Dict


class PubSubProcess:
    """
    Class defining a Flex PubSub Process followed by data acquisition.
    Note that messages are NOT acknowledged when running in debug
    mode. Use this mode during development to preserve message integrity.
    This class is generalized to not only publish but
    listening will be modified to perform a job based on the received message as well.

    Attributes
    ----------
    publish_to : str
        Topic ID for publishing self.new_message to. Defaults to None.
    project : str
        Defines Google Cloud project name.
    bucket_name : str
        Bucket name to upload the data to

    Methods
    -------
    publish_message(payload)
        Publishes messages as defined during init. Payload is a dict with extra information.
    """

    def __init__(
        self,
        date_str: str,
        time_str: str,
        basepath: str,
        metadata: Dict,
        cleanup_pipeline: bool = False,
        upload_letsgrow: bool = False,
        publish_to: str = "flex-dev",
        subscribe_to: str = "flex-dev-sub",
        project: str = "sobolt-plantfellow",
        bucket_name: str = "pf-flex-pipeline-test",
        verbose: bool = True,
    ):
        """
        __init__  init class for the pub/sub messaging service for acquisition

        Parameters
        ----------
        date_str : str
            date string of the uploaded file
        time_str : str
            time string of the uploaded file
        basename : str
            destination filepath (bucket filepath)
        metadata : Dict
            metadata info as a Dict
        cleanup_pipeline : bool, optional
            clean up intermediate pipeline results, by default False
        upload_letsgrow : bool, optional
            upload pipeline results to LetsGrow, by default False
        publish_to : str, optional
            topic to publish to, by default 'flex-topic-test'
        project : str, optional
            project name, by default "sobolt-plantfellow"
        bucket_name : str
            gcp bucket name to check file for
        verbose : bool, optional
            run in verbose mode, by default False
        """

        self.publish_to = publish_to
        self.subscribe_to = subscribe_to
        self.project = project
        self.bucket_name = bucket_name
        self.basepath = basepath
        self.metadata = metadata
        self.date_str = date_str
        self.time_str = time_str
        self.verbose = verbose
        self.cleanup_pipeline = cleanup_pipeline
        self.upload_letsgrow = upload_letsgrow

        self.publisher = pubsub_v1.PublisherClient()

        self.subscriber = pubsub_v1.SubscriberClient()
        # The `subscription_path` method creates a fully qualified identifier
        # in the form `projects/{project_id}/subscriptions/{subscription_id}`
        self.subscription_path = self.subscriber.subscription_path(
            self.project, self.subscribe_to
        )

    def publish_message_to_topic(self):
        """Publishes a general message to pubsub. Payload is a dict with extra
        information, and cannot contain the key 'data'.
        """
        # Encode data in UTF-8/bytestring with
        data = f"Data payload sent in serialised form. Data: {1}"
        data = data.encode("utf-8")  # type:ignore

        # Get UTC datetime in RFC 3339 code (like google does)
        d = datetime.now(timezone("CET"))
        dt_str = d.isoformat("T") + "Z"

        # Add various attributes to the message
        exdict = {
            "eventTime": f"{dt_str}",
            "eventType": "OBJECT_EXISTS",
            "payloadFormat": "CUSTOM",
            "bucketId": f"{self.bucket_name}",
            "date_str": f"{self.date_str}",
            "time_str": f"{self.time_str}",
            "basepath": f"{self.basepath}",
            "metadata": self.metadata["fileinfo"],
            "file_type": self.metadata["filetype"],
            "visard_id": self.metadata["visardid"],
            "plant_id": self.metadata["plantid"],
            "path_id": self.metadata["pathid"],
            "cleanup_pipeline": f"{self.cleanup_pipeline}",
            "upload_letsgrow": f"{self.upload_letsgrow}",
        }

        # TODO: if the dict is too big, split it
        payload = exdict

        # Get topic path and publish!
        topic_path = self.publisher.topic_path(self.project, self.publish_to)

        self._print_verbose(f"Publishing message to {self.project}/{self.publish_to}")

        future = self.publisher.publish(
            topic_path, data, origin="pubsubprocess.py", username="gcp", **payload
        )

        self._print_verbose(
            f"INFO in gcp_pubsub_publish_payload: Result of publishing: {future.result()}"
        )

    def acknowledge_messages(self, download_from_message, timeout: int = 300):
        """
        acknowledge_messages

        Parameters
        ----------
        download_from_message :
            Function to execute while ackoledging the message
        timeout : int, optional
            Keep listening for, by default 600
        """

        streaming_pull_future = self.subscriber.subscribe(
            self.subscription_path, callback=download_from_message
        )
        print(f"Listening for messages on {self.subscription_path}..\n")

        # Wrap subscriber in a 'with' block to automatically call close() when done.
        with self.subscriber:
            try:
                # When `timeout` is not set, result() will block indefinitely,
                # unless an exception is encountered first.
                result = streaming_pull_future.result(timeout=timeout)
                print(result)
            except TimeoutError:
                streaming_pull_future.cancel()  # Trigger the shutdown.
                streaming_pull_future.result()  # Block until the shutdown is complete.

    @staticmethod
    def split_list_by_serialised_len(input_list: list, input_str_len: int) -> List:
        """split a list based on limit

        Parameters
        ----------
        input_list : list
            list to be splitted
        input_str_len : int
            limit length

        Returns
        -------
        list
            splitted list into list of lists based on the limit
        """
        list_str_length = len(f"{input_list}")

        # Return unchanged if serialised length is less than input limit
        if list_str_length <= input_str_len:
            return [input_list]

        list_of_filelists = []

        num_files = len(input_list)
        num_to_split_list_by = ceil(len(f"{input_list}") / input_str_len)
        num_files_per_list = round(num_files / num_to_split_list_by)

        for i in range(num_to_split_list_by):
            start_ind = i * num_files_per_list
            if i == (num_to_split_list_by - 1):
                end_ind = num_files
            else:
                end_ind = (i + 1) * num_files_per_list

            list_of_filelists.append(input_list[start_ind:end_ind])

        return list_of_filelists

    @staticmethod
    def append_metadata_to_pubsub_dict(
        input_dict: dict, input_list: list, input_key: str
    ) -> dict:
        """append_metadata_to_pubsub_dict

        Parameters
        ----------
        input_dict : dict
            input message as dictionary
        input_list : list
            input list
        input_key : str
            keys

        Returns
        -------
        dict
            output dictionary
        """
        key_name = f"{input_key}"
        input_dict[key_name] = f"{input_list[0]}"
        for ind, input_filelist in enumerate(input_list[1:]):
            key_name = f"{input_key}_{ind}"
            input_dict[key_name] = f"{input_filelist}"
        return input_dict

    def _print_verbose(self, *args, **kwargs):
        """Print message if verbose is turned on"""
        if self.verbose:
            print(*args, **kwargs)
