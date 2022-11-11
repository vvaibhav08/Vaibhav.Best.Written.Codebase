import os, traceback
from os.path import join, basename, exists
import pandas as pd
from typing import Dict, List, Tuple, Any
from celery import Celery
from celery.utils.log import get_task_logger
import numpy as np

from main import Measure

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


@app.task(name="tasks.measure", serializer="json")
def measure(task_info: Dict) -> Dict:
    """
    measure worker
    Takes in  a task_info dictionary containing file to process,
    and some meta. Run the measuring process and updates the task_info
    with output file

    Parameters
    ----------
    task_info : Dict
        Task dictionary. This contains the file path, and metadata

    Returns
    -------
    Dict
        Task dictionary, updated with the filepath replaced with the output.
        The worker returns a csv with all the measurements for the plant in the given file
        This dict can be used by the next worker in chain of the celery pipeline
    """
    new_task_info = task_info.copy()

    # Fetch segmentation files from task_info
    segmentation_paths = [f for f in task_info["files"] if f["source"] == "SEGMENTATION"]
    assert (
        len(segmentation_paths) > 0
    ), f"Something went wrong, no file with source 'SEGMENTATION' found in task_info object!\n{task_info}"
    segmented_las = segmentation_paths[0]["path"]

    # Fetch settings from task_info
    metadata = task_info["settings"]["metadata"]
    file_type = task_info["settings"]["filetype"]
    visard_id = task_info["settings"]["visard_id"]
    plant_id = task_info["settings"]["plant_id"]
    path_id = task_info["settings"]["path_id"]
    overwrite_option = task_info["settings"]["overwrite"]
    debug = task_info["settings"]["debug"]

    # Prepare output folder
    output_folder = str(os.getenv("PIPELINE_OUTPUT_FOLDER"))
    data_output_dir = join(output_folder, "3.measuring")
    os.makedirs(data_output_dir, exist_ok=True)

    # Prepare error log folder + path
    error_log_dir = join(output_folder, "errors")
    os.makedirs(error_log_dir, exist_ok=True)
    error_log_path = join(
        error_log_dir, f"3.measuring_{basename(segmented_las)}_error.txt"
    )

    raw_las_name = basename(segmented_las).split(".")[0]
    output_path = join(data_output_dir, f"{raw_las_name}_measured.csv")

    try:
        m = Measure(
            segmented_las,
            data_output_dir,
            debug=debug,
            silent=False,
        )

        dict = {
            "rc_visard_id": visard_id,
            "path_number": path_id,
            "plant_number": plant_id,
            "file_type": file_type,
            "tomato_setting": None,
            "flower_setting": None,
            "circumference": None,
            "leaf_area": None,
            "length": None,
            "width": None,
            "stem_color_R": None,
            "stem_color_B": None,
            "stem_color_G": None,
        }

        if file_type.lower() == "kop":
            # Measure head circumference
            circum, _ = m.measure_head_circumference()

            # Measure average color and visualize result
            avg_R, avg_G, avg_B = m.extract_color(apply_normalization=True)

            dict["circumference"] = circum
            dict["stem_color_R"] = avg_R
            dict["stem_color_B"] = avg_B
            dict["stem_color_G"] = avg_G

        elif file_type.lower() == "blad":
            # Measure leaf dimensions and area
            leaf_area, length, width = m.measure_leaf_area()

            dict["leaf_area"] = leaf_area
            dict["length"] = length
            dict["width"] = width

        elif file_type.lower() == "tros":
            # Measure tomato setting and visualize results
            tomato_setting, _ = m.measure_tomato_setting()

            # Measure flower setting and visualize results
            flower_setting, _ = m.measure_flower_setting()

            dict["tomato_setting"] = tomato_setting
            dict["flower_setting"] = flower_setting

        else:
            print(f"Incorrect file type: {file_type}")

        # save results in a csv file
        df = pd.DataFrame(dict, index=[0])
        df.to_csv(output_path)

        assert exists(output_path), f"ERROR: Output file of measuring "
        new_task_info["files"].append({"path": output_path, "source": "MEASUREMENT_CSV"})

        return new_task_info
    except Exception as e:
        error_message = traceback.format_exc()
        with open(error_log_path, "w") as f:
            f.write(error_message)
        print(error_message)

        return new_task_info


@app.task(name="tasks.measure_multiple_frames", serializer="json")
def measure_multiple_frames(task_info: Dict) -> Dict:
    """
    measure worker
    Takes in  a task_info dictionary containing multiple segmented files to
    process and some meta. Run the measuring process on all segmented files
    and updates the task_info with output file.

    Parameters
    ----------
    task_info : Dict
        Task dictionary. This contains the file path, and metadata

    Returns
    -------
    Dict
        Task dictionary, updated with the filepath replaced with the output.
        The worker returns a csv with all the measurements for the plant in the given file
        This dict can be used by the next worker in chain of the celery pipeline
    """
    new_task_info = task_info.copy()

    # Fetch segmentation files from task_info
    segmentation_files = [f for f in task_info["files"] if f["source"] == "SEGMENTATION"]
    assert (
        len(segmentation_files) > 0
    ), f"Something went wrong, no file with source 'SEGMENTATION' found in task_info object!\n{task_info}"
    segmented_las_paths = [p["path"] for p in segmentation_files]

    # Fetch settings from task_info
    metadata = task_info["settings"]["metadata"]
    file_type = task_info["settings"]["filetype"]
    visard_id = task_info["settings"]["visard_id"]
    plant_id = task_info["settings"]["plant_id"]
    path_id = task_info["settings"]["path_id"]
    overwrite_option = task_info["settings"]["overwrite"]
    debug = task_info["settings"]["debug"]

    # Prepare output folder
    output_folder = str(os.getenv("PIPELINE_OUTPUT_FOLDER"))
    data_output_dir = join(output_folder, "3.measuring")
    os.makedirs(data_output_dir, exist_ok=True)

    # Prepare error log folder + path
    error_log_dir = join(output_folder, "errors")
    os.makedirs(error_log_dir, exist_ok=True)

    try:
        tomato_settings = []
        flower_settings = []
        stem_diameters = []
        leaf_areas = []
        leaf_lengths = []
        leaf_widths = []
        avg_Rs = []
        avg_Gs = []
        avg_Bs = []

        dict = {
            "rc_visard_id": visard_id,
            "path_number": path_id,
            "plant_number": plant_id,
            "file_type": file_type,
            "tomato_setting": None,
            "flower_setting": None,
            "circumference": None,
            "leaf_area": None,
            "length": None,
            "width": None,
            "stem_color_R": None,
            "stem_color_B": None,
            "stem_color_G": None,
        }

        # Get measurements of all segmented las files
        for segmented_las_path in segmented_las_paths:
            error_log_path = join(
                error_log_dir, f"3.measuring_{basename(segmented_las_path)}_error.txt"
            )

            raw_las_name = basename(segmented_las_path).split(".")[0]
            output_path = join(data_output_dir, f"{raw_las_name}_measured.csv")

            m = Measure(
                segmented_las_path,
                data_output_dir,
                debug=debug,
                silent=False,
            )

            if file_type.lower() == "kop":
                # Measure head circumference
                _, stem_diameters_file = m.measure_head_circumference()
                stem_diameters.extend(stem_diameters_file)

                # Measure average color and visualize result
                avg_R, avg_G, avg_B = m.extract_color(apply_normalization=True)
                avg_Rs.append(avg_R)
                avg_Gs.append(avg_G)
                avg_Bs.append(avg_B)

            elif file_type.lower() == "blad":
                # Measure leaf area, length and width
                leaf_area, length, width = m.measure_leaf_area()
                leaf_areas.append(leaf_area)
                leaf_lengths.append(length)
                leaf_widths.append(width)

            elif file_type.lower() == "tros":
                # Measure tomato setting and visualize results
                tomato_setting, _ = m.measure_tomato_setting()
                tomato_settings.append(tomato_setting)

                # Measure flower setting and visualize results
                flower_setting, _ = m.measure_flower_setting()
                flower_settings.append(flower_setting)
            else:
                print(f"Incorrect file type: {file_type}")

        if file_type.lower() == "kop":
            print(f"stem_diameters: {stem_diameters}")
            stem_diameters = Measure.remove_stem_diameter_outliers(stem_diameters)
            print(f"stem_diameters (no outliers): {stem_diameters}")
            circumference = Measure.calculate_circumference(np.median(stem_diameters))

            dict["circumference"] = circumference
            dict["stem_color_R"] = np.median(avg_Rs)
            dict["stem_color_B"] = np.median(avg_Bs)
            dict["stem_color_G"] = np.median(avg_Gs)

        elif file_type.lower() == "blad":
            dict["leaf_area"] = np.median(leaf_areas)
            dict["length"] = np.median(leaf_lengths)
            dict["width"] = np.median(leaf_widths)

        elif file_type.lower() == "tros":
            dict["tomato_setting"] = np.median(tomato_settings)
            dict["flower_setting"] = np.median(flower_settings)

        # merge and save results in a csv file
        df = pd.DataFrame(dict, index=[0])
        df.to_csv(output_path)

        assert exists(output_path), f"ERROR: Output file of measuring "
        new_task_info["files"].append({"path": output_path, "source": "MEASUREMENT_CSV"})

        return new_task_info
    except Exception as e:
        error_message = traceback.format_exc()
        with open(error_log_path, "w") as f:
            f.write(error_message)
        print(error_message)

        return new_task_info
