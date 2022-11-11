import os, argparse, sys
import traceback
from glob import glob
import shutil
from skimage import exposure
import open3d as o3d
import numpy as np
import pylas
from pathlib import Path
import struct
import math
import copy
from typing import List
import statistics
from pydantic import BaseModel
from os.path import join, basename, dirname, exists
import subprocess

from las_handler import LAS_HANDLER

MINIMAL_POINTS = 10000


class FileDict(BaseModel):
    file_path: str
    size: int
    point_count: int
    suitable: bool = False


class Preprocessor:
    """
    This class preprocesses the files present in the .zip to a .ply, optionally normalizes the color, saves it to a las file, and returns the path to the .las file.

    """

    # Parameters that define the center of a capture (for noise filtering)
    MAX_DISTANCE = 0.5
    BOUND_X = 0.2
    BOUND_Y = 0.2

    def __init__(
        self,
        rc_visard_zip_path: str,
        output_dir: str,
        filter_noise: bool = False,
        debug: bool = True,
        silent: bool = False,
        overwrite: bool = True,
    ):
        """
        __init__ Initialization of a Measure object

        Parameters
        ----------
        rc_visard_zip_path : str
            path of the zip file to be preprocessed
        output_dir : str
            path to the directory where the preprocessed file should be saved
        filter_noise : bool, optional
            Automatically filter noise from preprocessed point cloud by removing
            points that are not in the center of the capture. By default False.
            Center of the capture is defined by the MAX_DISTANCE, BOUND_X and BOUND_Y
            parameters.
        debug : bool, optional
            debug mode, by default True
        silent : bool, optional
            silent mode, by default False
        overwrite : bool, optional
            Overwrite preproces files if they already exist, by default True
        """

        self.rc_visard_zip_path = rc_visard_zip_path
        self.output_dir = output_dir

        self.base_filename = basename(self.rc_visard_zip_path).split(".")[0]
        self.preprocessed_folder_name = f"{self.base_filename}_preprocessed"

        # Pathto the folder with the preprocessed/normalized .las files
        self.preprocessed_folder_path = join(
            self.output_dir, self.preprocessed_folder_name
        )
        self.filter_noise = filter_noise
        self.debug = debug
        self.silent = silent
        self.overwrite = overwrite
        self.las_handler = LAS_HANDLER()

    def create_best_pointcloud(self) -> str:
        """Processes a .zip file containing disparities and intensities to .ply files.

        Returns
        -------
        str
            Path to .ply file
        """
        os.makedirs(self.preprocessed_folder_path, exist_ok=True)

        # 1. unzip rc-visard data
        dir_tmp = join(dirname(self.rc_visard_zip_path), f"{self.base_filename}_tmp")
        os.makedirs(dir_tmp, exist_ok=True)
        shutil.unpack_archive(self.rc_visard_zip_path, dir_tmp)
        pfm_filepaths = [
            join(dir_tmp, f) for f in os.listdir(dir_tmp) if f.endswith(".pfm")
        ]
        assert (
            len(pfm_filepaths) >= 1
        ), f"No .pfm files found in rc-visard .zip file '{self.rc_visard_zip_path}'"

        # 2. select suitable pfm file based on size, point count and colours
        suitable_pfm_files = self._select_pfm_files(pfm_filepaths)
        assert (
            len(suitable_pfm_files) > 0
        ), f"No suitable .pfm files found in rc-visard .zip file '{self.rc_visard_zip_path}'"
        suitable_pfm_file = suitable_pfm_files[0]
        print("selected file", suitable_pfm_file)

        # 3. Convert to .ply, and copy intensity files
        ply_paths = self.pfm_to_ply([suitable_pfm_file], self.preprocessed_folder_path)

        # 4. Remove tmp files
        if not self.debug:
            shutil.rmtree(dir_tmp)

        return ply_paths[0]

    def create_pointclouds(self, select_suitable: bool = False) -> List[str]:
        """Processes a .zip file containing disparities and intensities to .ply files.

        Parameters
        ----------
        select_suitable : bool, optional
            Select suitable frames based on files size and color distribution
            of data, by default False

        Returns
        -------
        List[str]
            List of paths to .ply files
        """
        os.makedirs(self.preprocessed_folder_path, exist_ok=True)

        # 1. unzip rc-visard data
        dir_tmp = join(dirname(self.rc_visard_zip_path), f"{self.base_filename}_tmp")
        os.makedirs(dir_tmp, exist_ok=True)
        shutil.unpack_archive(self.rc_visard_zip_path, dir_tmp)
        pfm_filepaths = [
            join(dir_tmp, f) for f in os.listdir(dir_tmp) if f.endswith(".pfm")
        ]
        assert (
            len(pfm_filepaths) >= 1
        ), f"No .pfm files found in rc-visard .zip file '{self.rc_visard_zip_path}'"

        # 2. select suitable pfm file based on size, point count and colours
        suitable_pfm_files = [
            FileDict(
                file_path=f,
                size=int(os.stat(f).st_size),
                point_count=-1,
                suitable=True,
            )
            for f in pfm_filepaths
        ]
        if select_suitable:
            suitable_pfm_files = self._select_pfm_files(pfm_filepaths)
            assert (
                len(suitable_pfm_files) > 0
            ), f"No suitable .pfm files found in rc-visard .zip file '{self.rc_visard_zip_path}'"
            print(f"Found {len(suitable_pfm_files)} suitable files!")

        # 3. Convert to .ply, and copy intensity files
        ply_paths = self.pfm_to_ply(suitable_pfm_files, self.preprocessed_folder_path)

        # 4. Remove tmp files
        if not self.debug:
            shutil.rmtree(dir_tmp)

        return ply_paths

    def _select_pfm_files(self, pfm_filepaths: List[str]) -> List[FileDict]:
        """Chooses a suitable pfm file from a list of files, based on:
        - time stamp. Dependent on the number of files, the first and last (2) files are removed,
        due to assumed starting up and finishing time.
        - file size (in bytes). Prefers files that don't deviate more than 10% from the average size.
        - point count. Excludes files with less than 10.000 points, prefers files that don't deviate
        more than 10% in point count.
        - colour range (TEMPORARILY DISABLED). If multiple options are left, the file is chosen with the highest colour range

        First the function excludes files that are not usable, based on the size, point count and
        over/undersaturation. From the remaining files, the most suitable files are chosen based on
        the files that don't deviate more than 10% from the average in file size or point count.

        If multiple files are suitable, the middle file is chosen.

        When file size/point counts of all files are 0, an exception is raised.

        Parameters
        ----------
        pfm_filepaths : List[str]
            List of pfm file names

        Returns
        -------
        List[FileDict]
            List of suitable point cloud files.

        Raises
        ------
        Exception
            "InputError: none of the pfm files contain any data." is raised when the file size and/or
            point counts of all inputted files are 0.
        """

        # first sort on timestamp
        pfm_filepaths.sort()

        # remove first and last files
        if len(pfm_filepaths) > 10:
            pfm_filepaths = pfm_filepaths[2 : len(pfm_filepaths) - 2]
        elif len(pfm_filepaths) > 5:
            pfm_filepaths = pfm_filepaths[1 : len(pfm_filepaths) - 1]

        # get parameters for each file
        pfm: List[FileDict] = [
            FileDict(
                file_path=path,
                size=int(os.stat(path).st_size),
                point_count=int(self.read_pfm(path)),
                suitable=False,
            )
            for path in pfm_filepaths
        ]

        # determine average and max-deviation in file size (in bytes)
        average = sum(f.size for f in pfm) / len(pfm)
        max_deviation = average * 0.1

        # determine average and max-deviation in number of points
        average_points = sum(f.point_count for f in pfm) / len(pfm)
        max_deviation_points = average_points * 0.1

        if average == 0 or average_points == 0:
            raise Exception(f"InputError: none of the pfm files contain any data.")

        # step 1: eliminate non-usable files
        remove_unusable = []
        for idx, f in enumerate(pfm):

            # check if the file is usable
            if not self.check_pfm_usability(f.size, f.point_count):
                # remove non-usable files from all consideration
                remove_unusable.append(pfm.index(f))

        for i in reversed(remove_unusable):
            pfm.remove(pfm[i])

        # step 2: find optimal files
        for idx, f in enumerate(pfm):
            # if a file size deviates more than 10% from the average file size, it's not the most suitable
            if f.size > average + max_deviation or f.size < average - max_deviation:
                f.suitable = False
            # if the point cloud deviates more than 10% from the average point cloud, it's not the most suitable
            elif (
                f.point_count > average_points + max_deviation_points
                or f.point_count < average_points - max_deviation_points
            ):
                f.suitable = False
            else:
                f.suitable = True

        # get list of the files that are suitable
        suitable_files = [f for f in pfm if f.suitable == True]

        # if no files are left at all, return an error
        if not len(pfm):
            raise Exception(f"InputError: there are no suitable files!")
        # if not files are suitable, but are optional, return file that has the median number of points
        elif len(suitable_files) == 0:
            point_counts_ = [f.point_count for f in pfm]
            median_points = statistics.median_high(point_counts_)
            file_idx = point_counts_.index(median_points)
            return [pfm[file_idx]]

        return suitable_files

    def check_pfm_usability(self, file_size, point_count) -> bool:
        """Returns whether a file size, point cloud and (TEMPORARILY REMOVED) average RBG value
        are usable to perform an analysis on.

        Parameters
        ----------
        file_size : int
            Size of file in bytes
        point_count : int
            Number of points in the point cloud in the file

        Returns
        -------
        bool
            False if not usable, True if usable
        """
        if file_size == 0 or point_count < MINIMAL_POINTS:
            return False
        else:
            return True

    def read_pfm(self, filename: str):
        """
        Reads an pfm file and decodes it. Determines the colour range in the file (either of grayscale
        or RGB) by returning the minimum and maximum colour values, and returns the number of points in the
        file.

        Parameters
        ----------
        filename : str
            Path to the file to read

        Returns
        -------
        point count
            Number of points in the file (with values, no empty points)
        """

        with Path(filename).open("rb") as pfm_file:

            line1, line2, line3 = (
                pfm_file.readline().decode("latin-1").strip() for _ in range(3)
            )
            assert line1 in ("PF", "Pf")

            channels = 3 if "PF" in line1 else 1
            width, height = (int(s) for s in line2.split())
            scale_endianess = float(line3)
            bigendian = scale_endianess > 0
            scale = abs(scale_endianess)

            buffer = pfm_file.read()
            samples = width * height * channels
            assert len(buffer) == samples * 4

            fmt = f'{"<>"[bigendian]}{samples}f'
            decoded = struct.unpack(fmt, buffer)
            shape = (height, width, 3) if channels == 3 else (height, width)
            decoded_inf = [x for x in decoded if not math.isinf(x)]
            count = sum(map(lambda x: not math.isinf(x), decoded))

            # return np.flipud(np.reshape(decoded, shape)) * scale
            return count

    def pfm_to_ply(
        self,
        pfm_files: List[FileDict],
        output_folder: str,
        zip_result: bool = False,
    ) -> List[str]:
        """
        pfm_to_ply
        Convert pfm rc_visard stereo depth files to point cloud ply files

        Parameters
        ----------
        pfm_files : List[FileDict]
            pfm files
        output_folder : str
            output folder
        zip_result : bool, optional
            option to zip output, by default False

        Returns
        -------
        List[str]
            List of paths to the created .ply files
        """
        print(f"Processing and placing files in {output_folder}")

        # Loop over each file and create pointcloud using the plycmd script from cvkit
        output_ply_files = []
        for i, pfm_file in enumerate(pfm_files):
            input_folder = dirname(pfm_file.file_path)

            print(f"Building {i+1}/{len(pfm_files)} point clouds")
            output_ply_path = join(output_folder, f"{pfm_file.file_path[:-20]}.ply")
            temp_ply_basename = basename(output_ply_path)
            temp_ply_path = join(input_folder, temp_ply_basename)

            # Skip file if self.overwrite is False and file already exists.
            if not self.overwrite and exists(output_ply_path):
                output_ply_files.append(output_ply_path)
                continue

            try:
                cmd_result = subprocess.run(
                    [
                        "plycmd",
                        basename(pfm_file.file_path),
                        "-ascii",
                        temp_ply_basename,
                    ],
                    stdout=subprocess.PIPE,
                    cwd=input_folder,
                )

                # Replace [diffuse_red, diffuse_green, diffuse_blue] with [red, blue, green] in file so open3d parses the color correctly
                with open(temp_ply_path, "r") as f:
                    newText = (
                        f.read()
                        .replace("diffuse_red", "red")
                        .replace("diffuse_green", "green")
                        .replace("diffuse_blue", "blue")
                    )

                with open(output_ply_path, "w") as f:
                    f.write(newText)

                # Copy intensity files to output_folder
                # Get name of intensity and intensityRight files:
                intensity_left_filename = (
                    pfm_file.file_path.split("_Disparity_00_00.pfm")[0]
                    + "_Intensity_00_00.ppm"
                )
                intensity_right_filename = (
                    pfm_file.file_path.split("_Disparity_00_00.pfm")[0]
                    + "_IntensityRight_00_00.ppm"
                )

                shutil.copy(join(input_folder, intensity_left_filename), output_folder)
                shutil.copy(join(input_folder, intensity_right_filename), output_folder)

                output_ply_files.append(output_ply_path)
            except Exception as e:
                error_message = traceback.format_exc()
                print(
                    f"Not using this frame, cause something is wrong here: {pfm_file.file_path}"
                )
                print(error_message)

        # Zip output folder
        if zip_result:
            print("Zipping folder")
            try:
                shutil.make_archive(f"{output_folder}", "zip", output_folder)
            except Exception as e:
                error_message = traceback.format_exc()
                print(f"Error while zipping: {output_folder}.")
                print(error_message)

        return output_ply_files

    def ply_to_las(
        self, ply_files: List[str], normalize_colors: bool = True
    ) -> List[str]:
        """ply_to_las
        1. Convert ply files to las
        2. Filter out points based on distance from the camera

        Parameters
        ----------
        ply_files : List[str]
            List of paths to .ply files that should be converted
        normalize_colors : bool, optional
            Option to normalize color values with
            histogram-matching algorithm, by default True

        Returns
        -------
        List[str]
            List of paths to the converted .las files
        """
        output_las_filepaths: List[str] = []
        for ply_file in ply_files:
            ply_filepath = join(self.preprocessed_folder_path, ply_file)
            filename_frame = "_".join(basename(ply_filepath).split(".")[:-1])
            las_filepath = join(
                self.preprocessed_folder_path,
                f"{self.base_filename}_{filename_frame}.las",
            )

            # Skip file if self.overwrite is False and file already exists.
            if not self.overwrite and exists(las_filepath):
                output_las_filepaths.append(las_filepath)
                continue

            pcd = o3d.io.read_point_cloud(ply_filepath)

            # Normalize colors
            if normalize_colors:
                colors = self.normalize_color(
                    np.asarray(pcd.colors), "histogram-matching"
                )
            else:
                colors = np.asarray(pcd.colors)

            # get points
            points = np.asarray(pcd.points)

            # Filter points on location wrt the camera
            if self.filter_noise:

                distance_filter = points[:, 2] < self.MAX_DISTANCE
                center_filter_x = np.logical_and(
                    points[:, 0] < self.BOUND_X, points[:, 0] > -self.BOUND_X
                )
                center_filter_y = np.logical_and(
                    points[:, 1] < self.BOUND_Y, points[:, 1] > -self.BOUND_Y
                )
                merged_filter = np.logical_and(
                    np.logical_and(distance_filter, center_filter_x), center_filter_y
                )
                points = points[merged_filter]
                colors = colors[merged_filter]

            # Write data to .las file
            output_las_filepaths.append(las_filepath)
            self.las_handler.save(las_filepath, points, colors)

        return output_las_filepaths

    def normalize_color(self, colors, method="histogram-matching"):
        """Normalizes color values to a standard space using the specified method

        Parameters:
        -----------

        colors: np.array(n, 3)
            array of RGB colors
        method: str
            Method of color normalization. Options: [greyworld, gimp-wb, histogram-matching]

        Returns:
        --------
        normalized_colors: np.array(n, 3)
            array of normalized RGB colors
        """
        if method == "greyworld":
            print(f"Applying: {method}")
            colors = colors * 255.0

            # Calculate averages
            average_R = np.mean(colors[:, 0])
            average_G = np.mean(colors[:, 1])
            average_B = np.mean(colors[:, 2])

            # Scale color channel values by their averages
            colors[:, 0] = colors[:, 0] * (colors[:, 0] / average_R)
            colors[:, 1] = colors[:, 1] * (colors[:, 1] / average_G)
            colors[:, 2] = colors[:, 2] * (colors[:, 2] / average_B)

            print(f"Color averages: R: {average_R}, G: {average_G}, B: {average_B},")

            # Convert back to values between [0, 1]
            colors = colors / 255.0

        if method == "gimp-wb":
            print(f"Applying: {method}")
            """Apply the GIMP white-balance algorithm:
            https://docs.gimp.org/en/gimp-layer-white-balance.html"""

            # Convert to values between [0, 255]
            colors = colors * 255.0

            # white balance for every channel independently
            colors[:, 0] = whitebalance_channel(colors[:, 0])
            colors[:, 1] = whitebalance_channel(colors[:, 1])
            colors[:, 2] = whitebalance_channel(colors[:, 2])

            colors = colors / 255.0

        if method == "histogram-matching":
            print(f"Applying: {method}")

            # Load reference point cloud
            reference_path = "histograms/average_color.las"
            _, ref_colors, _ = self.las_handler.read_laz(reference_path)
            ref_colors = np.array(ref_colors, dtype=np.float64)

            colors = exposure.match_histograms(colors, ref_colors, channel_axis=1)

        return colors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Required arguments:
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        metavar="PATH",
        help="Input zip file",
        required=True,
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        metavar="DIR",
        help="Output directory",
        required=True,
    )
    # Optional arguments:
    parser.add_argument(
        "-b",
        "--best-only",
        action="store_true",
        help="Only create single best pointcloud",
    )
    parser.add_argument(
        "-f", "--filter-noise", action="store_true", help="Filter noise from point cloud"
    )
    parser.add_argument("-s", "--silent", action="store_true", help="Turn on silent mode")

    args = parser.parse_args()
    pre = Preprocessor(
        args.input,
        args.output,
        filter_noise=args.filter_noise,
        debug=True,
        silent=args.silent,
    )

    if args.best_only:
        ply_path = pre.create_best_pointcloud()
        pre.ply_to_las([ply_path])
    else:
        ply_paths = pre.create_pointclouds()
        pre.ply_to_las(ply_paths)
