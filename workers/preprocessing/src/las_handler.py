from typing import List, Tuple, Any
import numpy as np
import pylas


class LAS_HANDLER:
    def __init__(self, silent: bool = False):
        """Initialization of a Measure object

        Parameters
        ----------
        silent : bool, optional
            Silent mode, by default False
        """
        self._silent = silent

    def _print(self, *args, **kwargs):
        """Prints inputted arguments if silent mode is off."""
        if not self._silent:
            print(*args, **kwargs)

    @staticmethod
    def read_laz(laz_path: str) -> Tuple[Any, Any, Any]:
        """Read .las or .laz file.

        Parameters
        ----------
        laz_path : str
            Absolute path to a .las or .laz file

        Returns
        -------
        List[List]
            points, colors lists:
            - points: n,3 shaped list in XYZ format of float16 values
            - colors: n,3 shaped list in RGB format of float16 values between 0 and 1.
            - classification: Optional: Segmentation labels, if present
        """
        file_reader = pylas.read(laz_path)
        header = file_reader.header
        points = (
            np.vstack([file_reader.x, file_reader.y, file_reader.z])
            .transpose()
            .astype(np.float16)
        )

        if any(
            [
                spec == "red"
                for spec in file_reader.points_data.point_format.dimension_names
            ]
        ):
            rgb = [
                file_reader.red,
                file_reader.green,
                file_reader.blue,
            ]
        else:
            col = np.full(len(file_reader.x), 0)
            rgb = [col, col, file_reader.intensity]

        # Change color to right format (between 0 and 1)
        colors = (np.vstack(rgb).transpose()).astype(np.float16)

        classification = file_reader.classification.astype(np.int32)
        if classification.any() > 0:
            print("predictions present, hence using them..")
            return list(points), list(colors), list(classification)
        else:
            try:
                print("labels present, hence using them..")
                label = file_reader.label.astype(np.int32)
                return list(points), list(colors), list(label)
            except:
                print(f"No colors or labels present only loading points and colors")
                return list(points), list(colors), None

    @staticmethod
    def create(
        points: np.ndarray, colors: np.ndarray = None, classification: np.ndarray = None
    ) -> pylas.lasdatas.las12.LasData:
        """Create a pylas data object from a set of 3D points.

        Parameters
        ----------
        points : np.ndarray
            n,3 shaped numpy array with float values (in XYZ) format.
        colors : np.ndarray, optional
            n,3 shaped numpy array with float values between 0 and 1.
            Every value represents the intensity of a color (in RGB format),
            by default None
        classification : np.ndarray, optional
            n shaped numpy array with integer values representing
            the classification of every point, by default None

        Returns
        -------
        pylas.lasdatas.las12.LasData
            Pylas data object
        """
        outfile = pylas.create(point_format_id=2, file_version="1.2")

        points = np.asarray(points, dtype=np.float64)

        # Update header information
        outfile.header.scales = [0.0001, 0.0001, 0.0001]

        # Set point values
        outfile.x = points[:, 0]
        outfile.y = points[:, 1]
        outfile.z = points[:, 2]

        # Set classification if applicable
        if classification is not None:
            outfile.classification = classification

        # Set colors if applicable
        if colors is not None:
            outfile.red = colors[:, 0]
            outfile.green = colors[:, 1]
            outfile.blue = colors[:, 2]

        return outfile

    @staticmethod
    def save(
        outpath: str,
        points: np.ndarray,
        colors: Any = None,
        classification: np.ndarray = None,
    ) -> bool:
        """Save pointcloud data to a .las or .laz file.

        Parameters
        ----------
        outpath : str
            Path to output .las or .laz file
        points : np.ndarray
            n,3 shaped numpy array with float values (in XYZ) format.
        colors : np.ndarray, optional
            n,3 shaped numpy array with float values between 0 and 1.
            Every value represents the intensity of a color (in RGB format),
            by default None
        classification : np.ndarray, optional
            n shaped numpy array with integer values representing
            the classification of every point, by default None

        Returns
        -------
        bool
            Returns true when writing of the file was successful.
        """
        try:
            LAS_HANDLER.create(points, colors, classification).write(outpath)
        except:
            return False
        return True
