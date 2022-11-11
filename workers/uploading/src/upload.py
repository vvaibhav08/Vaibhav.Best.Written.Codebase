import sys
from letsgrow_helper import LetsGrowHelper
import pandas as pd
import datetime


class Uploader:
    """Class to perform uploading of measured data to the LetsGrow API."""

    def __init__(
        self,
        results_file_path: str,
        letsgrow_helper: LetsGrowHelper,
        debug: bool = True,
        silent: bool = False,
    ):
        """
        __init__ Initialization of an Uploader object. Parses the filename.

        Parameters
        ----------
        results_file_path: str
            Absolute path to the .csv file containing the measurement results.
        debug : bool, optional
            debug mode, by default True
        silent : bool, optional
            silent mode, by default False
        """
        self.results_file_path = results_file_path

        self.moduleId = 45237
        self.rc_visard_id = ""
        self.timestamp = ""
        self.file_type = ""
        self.tomato_type = ""
        self.path_number = ""
        self.plant_number = ""
        self.letsgrow_helper = letsgrow_helper

        self.parse_file_name()

        # Dictionary used to the select the relevant values based on the file type (Kop, Blad, Tros)
        self.relevant_values = {
            # 'Kop': ['circumference', 'stem_color_R', 'stem_color_B', 'stem_color_G'], # add back when implemented in letsgrow
            "Kop": ["circumference"],
            "Blad": ["leaf_area", "length", "width"],
            "Tros": ["tomato_setting", "flower_setting"],
        }

        # Dictionary linking our measurements to the LetsGrow colId's
        self.measurement_name_to_colid = {
            "circumference": 1673876,
            "leaf_area": 1673901,
            "length": 1673899,
            "width": 1673900,
            "tomato_setting": 1673894,
            "flower_setting": 1673887,
        }

    def parse_file_name(self):
        """Parses the filename and in order to extract all required information for the upload"""
        try:
            # Get file type:
            basename = self.results_file_path.split("/")[-1]

            basename_split = basename.split("_")

            # Get the serial number of the rc_visard
            self.rc_visard_id = basename.split("_")[1]

            # Extract the timestamp
            self.timestamp = (
                f"{basename.split('_')[2]}T{basename.split('_')[3].replace('-', ':')}"
            )

            # Get the file type, options: [Kop, Blad, Tros]
            self.file_type = basename.split("_")[4]

            print(basename)
            print(f'len basename split: {len(basename.split("_"))}')

            # Switch case dependent on how much information is present within the filename.
            # Only rc_visard serial number is known
            if len(basename.split("_")) == 6:
                self.instance_name = f"{self.rc_visard_id}"

            # Tomato type present
            elif len(basename.split("_")) == 7:
                self.tomato_type = basename.split("_")[5]
                self.instance_name = f"{self.rc_visard_id}_{self.tomato_type}"

            # Path and plant number present without tomato type
            elif len(basename.split("_")) == 10:
                self.path_number = basename.split("_")[6]
                self.plant_number = basename.split("_")[8]
                self.instance_name = f"{self.rc_visard_id}_pad_{self.path_number}_plant_{self.plant_number}"

            # Tomato type, path and plant number present
            elif len(basename.split("_")) == 11:
                # Note that we do not make the tomato type part of the instance name when path and plant numbers are present.
                # If these numbers are known, then the grower also knows which crop is growing there.
                self.path_number = basename.split("_")[7]
                self.plant_number = basename.split("_")[9]
                self.instance_name = f"{self.rc_visard_id}_pad_{self.path_number}_plant_{self.plant_number}"

            elif len(basename.split("_")) >= 14:
                # Note that we do not make the tomato type part of the instance name when path and plant numbers are present.
                # If these numbers are known, then the grower also knows which crop is growing there.
                self.path_number = basename.split("_")[7]
                self.plant_number = basename.split("_")[9]
                self.instance_name = f"{self.rc_visard_id}_pad_{self.path_number}_plant_{self.plant_number}"

            assert self.instance_name != "", print(
                "No plant or path number defined, omitting upload"
            )

        except Exception as e:
            print(f"Could not parse filename: {e}")

    def load_values(self) -> pd.DataFrame:
        """Loads values from the provided measurement results file. Checks if it contains data.

        Returns:
        --------
        df: pd.DataFrame
            Dataframe containing measured values.
        """
        df = pd.read_csv(self.results_file_path)

        assert len(df) >= 1, f"The .csv file contains no rows: {self.results_file_path}"
        assert (
            len(df.columns) >= 9
        ), f"Not all columns present in results file, expected 9 columns, but got: {len(df.columns)}"

        return df

    def get_or_create_letsgrow_instance(self) -> str:
        """Returns a LetsGrow instance. The instance is retrieved by querying the LetsGrow API based on the self.instance_name.
        If no instance is found for the self.instance_name, an instance is created.

        Returns:
        --------
        instance: dict
            The instance on the LetsGrow API
        """

        instance = self.letsgrow_helper.get_instance_by_name(
            self.moduleId, self.instance_name
        )

        if instance == None:
            self.letsgrow_helper.create_instance(
                self.moduleId, 0, self.instance_name, 0, 0
            )
            instance = self.letsgrow_helper.get_instance_by_name(
                self.moduleId, self.instance_name
            )

        print(f"instance_id: {instance}")

        return instance

    def upload(self, values):
        """Uploads the data in the provided dataframe to the LetsGrow API.

        Parameters:
        -----------
        values: pandas.DataFrame
            The dataframe containing all the measured values

        Returns:
        --------
        instanceId: str
            The instanceId of the instance on the LetsGrow API
        """
        instance = self.get_or_create_letsgrow_instance()

        # Loop over all relevant values for the current file_type
        for measurement_name, value in values[
            self.relevant_values[self.file_type]
        ].iteritems():
            colId = self.measurement_name_to_colid[measurement_name]

            resp = self.letsgrow_helper.put_value(
                moduleId=self.moduleId,
                colId=colId,
                instanceId=instance["Id"],
                name=self.instance_name,
                path=self.path_number if self.path_number != "" else 0,
                section=self.plant_number if self.plant_number != "" else 0,
                value=value[0],
                timestamp=self.timestamp,
            )


if __name__ == "__main__":
    lg = LetsGrowHelper()
    lg.login()

    results_file_path = "/home/jeroen.vranken/data/preprocess/processed/rc-visard_06784657_2022-04-14_08-56-26_Kop_preprocessed/image_1639130388_measured.csv"
    # results_file_path = '/home/jeroen.vranken/data/preprocess/processed/rc-visard_06784657_2022-06-02_07-36-05_Tros_Piccolo_preprocessed/image_1639130388_measured.csv'
    # results_file_path = '/home/jeroen.vranken/data/preprocess/processed/rc-visard_06784657_2022-09-08_10-15-53_Kop_Piccolo_pad_1_plant_3_transformed/image_1639130388_measured.csv'

    uploader = Uploader(results_file_path, lg)

    values = uploader.load_values()
    uploader.upload(values)
