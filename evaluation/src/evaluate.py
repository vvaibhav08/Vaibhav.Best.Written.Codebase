import os
import traceback
from os.path import exists
import argparse
import pandas as pd
import datetime
import numpy as np
from typing import Dict, List


class Evaluation:
    """Class to perform evaluation of measured data by comparing it to the validated data."""

    def __init__(
        self,
        predicted_measurements_path: str,
        true_measurements_path: str,
        monday_start: bool,
    ):
        """To initialize, we need the result file name and the validated data file name.
        It's saved as a pandas dataframe.

        Parameters
        ----------
        predicted_measurements_path : str
            Full path of file name of the results from the pipeline.
        true_measurements_path : str
            Full path of file name containing the validated data to compare our results to.
        """
        self.df_predicted = pd.read_csv(predicted_measurements_path)
        self.df_true = pd.read_csv(true_measurements_path)
        self.monday_start = monday_start

    def evaluate(self) -> pd.DataFrame:
        """Run evaluation on predicted and true measurements

        Returns
        -------
        pd.DataFrame
            Output evaluation dataframe containing the matching
            predicted-true measurements and evaluation metrics per
            plant
        """
        output_evaluation: Dict = {
            "rc_visard_id": [],
            "plant_number": [],
            "path_number": [],
            "date": [],
            "leaf_width_pred": [],
            "leaf_width_true": [],
            "leaf_width_MSE": [],
            "leaf_length_pred": [],
            "leaf_length_true": [],
            "leaf_length_MSE": [],
            "circumference_pred": [],
            "circumference_true": [],
            "head_length_true": [],
            "head_width_true": [],
            "circumference_MSE": [],
            "circumference_MSE_2": [],
            "tomato_setting_pred": [],
            "tomato_setting_true": [],
            "tomato_setting_MSE": [],
            "flower_setting_pred": [],
            "flower_setting_true": [],
            "flower_setting_MSE": [],
        }
        skipped_count = 0

        # Iterate of predictions
        for i, row in self.df_predicted.iterrows():

            # 1. Find matching true measurements
            matches = self._find_matching_true_measurements(
                row.path_number, row.plant_number, row.date, row.rc_visard_id
            )
            if len(matches) == 0:
                print(
                    f"No True measurements found for plant:{row.plant_number}, path:{row.path_number}, date:{row.date}, rc_visard:{row.rc_visard_id}! Skipping this prediction."
                )
                skipped_count += 1
                continue
            if len(matches) > 1:
                print(
                    f"WARNING: {len(matches)} matching true measurements were found for plant:{row.plant_number}, path:{row.path_number}, date:{row.date}, rc_visard:{row.rc_visard_id}! Using the first match..."
                )

            # 2. Gather matched measurements into variables
            leaf_width_pred = row.width
            leaf_width_true = matches.leaf_width.values[0]
            leaf_length_pred = row.length
            leaf_length_true = matches.leaf_length.values[0]
            circumference_pred = row.circumference
            circumference_true = matches.circumference.values[0]
            head_length_true = matches.head_length.values[0]
            head_width_true = matches.head_width.values[0]
            tomato_setting_pred = row.tomato_setting
            tomato_setting_true = matches.tomato_setting.values[0]
            flower_setting_pred = row.flower_setting
            flower_setting_true = matches.flower_setting.values[0]

            # 3. Append predictions and matching true measurements to output
            output_evaluation["rc_visard_id"].append(row.rc_visard_id)
            output_evaluation["plant_number"].append(row.plant_number)
            output_evaluation["path_number"].append(row.path_number)
            output_evaluation["date"].append(row.date)
            output_evaluation["leaf_width_pred"].append(leaf_width_pred)
            output_evaluation["leaf_width_true"].append(leaf_width_true)
            output_evaluation["leaf_length_pred"].append(leaf_length_pred)
            output_evaluation["leaf_length_true"].append(leaf_length_true)
            output_evaluation["circumference_pred"].append(circumference_pred)
            output_evaluation["circumference_true"].append(circumference_true)
            output_evaluation["head_length_true"].append(head_length_true)
            output_evaluation["head_width_true"].append(head_width_true)
            output_evaluation["tomato_setting_pred"].append(tomato_setting_pred)
            output_evaluation["tomato_setting_true"].append(tomato_setting_true)
            output_evaluation["flower_setting_pred"].append(flower_setting_pred)
            output_evaluation["flower_setting_true"].append(flower_setting_true)

            # 4. Evaluate measurements
            MSE_leaf_width = self._mean_square_error(leaf_width_true, leaf_width_pred)
            MSE_leaf_length = self._mean_square_error(leaf_length_true, leaf_length_pred)
            MSE_circumference_2 = self._mean_square_error(
                circumference_true, circumference_pred
            )
            MSE_circumference = self._calculate_circumference_error(
                circumference_pred, matches
            )
            MSE_tomato_setting = self._mean_square_error(
                tomato_setting_true, tomato_setting_pred
            )
            MSE_flower_setting = self._mean_square_error(
                flower_setting_true, flower_setting_pred
            )
            output_evaluation["leaf_width_MSE"].append(MSE_leaf_width)
            output_evaluation["leaf_length_MSE"].append(MSE_leaf_length)
            output_evaluation["circumference_MSE"].append(MSE_circumference)
            output_evaluation["circumference_MSE_2"].append(MSE_circumference_2)
            output_evaluation["tomato_setting_MSE"].append(MSE_tomato_setting)
            output_evaluation["flower_setting_MSE"].append(MSE_flower_setting)

        df_eval = pd.DataFrame(output_evaluation)

        if skipped_count:
            print(
                f"Skipped {skipped_count} predictions in total, because no matching true measurements were found"
            )
        return df_eval

    def _find_matching_true_measurements(
        self, path_number: int, plant_number: int, date: str, rc_visard_id: str
    ) -> pd.DataFrame:
        """Matches the data from the result file from the pipeline to the validated data.

        Parameters
        ----------
        path_number : int
            Path where the plant is located
        plant_number : int
            Number of the plant
        date : str
            the acquistion date (the validated data only contained week numbers, not dates, so the
            first monday of each week is taken. The result date will therefore be adjusted to the previous
        rc_visard_id : str
            Serial number of the used rc-visard device

        Returns
        -------
        pd.DataFrame
            The matching true measurements
        """
        # # set date to a date type
        # dt_date = datetime.datetime.strptime(date, "%Y-%m-%d")

        if self.monday_start:
            # get previous monday of the date: all validated measurements are set to the first monday of the week
            dt_date = datetime.datetime.strptime(date, "%Y-%m-%d")
            weekday = dt_date.weekday()
            date = (dt_date - datetime.timedelta(days=weekday)).strftime("%Y-%m-%d")

        df = self.df_true  # short alias to avoid coding
        matching_true_measurements = df.loc[
            (df["date"] == date)
            & (df["rc_visard_id"] == int(rc_visard_id))
            & (df["path_number"] == float(path_number))
            & (df["plant_number"] == float(plant_number))
        ]

        return matching_true_measurements

    def _calculate_circumference_error(
        self, pred_circumference: float, df_true_matches: pd.DataFrame
    ) -> float:
        """Get the MSE of the circumference result from the pipeline, as compared to the validated data.
        The validated data only has head_width and head_length, so this is translated to the circumference
        first.

        Returns
        -------
        float
            Mean Square Error of the result circumference compared to the validated circumference.
        """
        val_diameter = (
            df_true_matches["head_length"].values[0]
            + df_true_matches["head_width"].values[0]
        ) / 2
        val_circumference = val_diameter * np.pi
        return self._mean_square_error(val_circumference, pred_circumference)

    def _mean_square_error(self, true: float, pred: float) -> float:
        """Returns the Mean Square Error.

        Parameters
        ----------
        true : float
            true value
        pred : float
            predicted value

        Returns
        -------
        float
            Mean Square Error.
        """
        # the result is divided by the true value + a very small number, to avoid dividing by 0
        return abs(true - pred) / (true + 0.000001)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Required arguments:
    parser.add_argument(
        "-t",
        "--true-measurements",
        type=str,
        metavar="PATH",
        help="csv file",
        required=True,
    )
    parser.add_argument(
        "-p",
        "--predicted-measurements",
        type=str,
        metavar="PATH",
        help="csv file",
        required=True,
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        metavar="PATH",
        help="csv file",
        required=True,
    )
    parser.add_argument(
        "--monday-start",
        action="store_true",
        help="True if the true measurement dates start on the monday of the week",
        default=False,
        required=False,
    )

    args = parser.parse_args()

    assert exists(
        args.true_measurements
    ), f"file at '{args.true_measurements}' does not exist!"
    assert exists(
        args.predicted_measurements
    ), f"file at '{args.predicted_measurements}' does not exist!"

    eval = Evaluation(
        args.predicted_measurements, args.true_measurements, args.monday_start
    )

    df_eval = eval.evaluate()
    df_eval.to_excel(args.output, index=False)
