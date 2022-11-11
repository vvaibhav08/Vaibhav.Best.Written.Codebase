import os
import numpy as np

from las_handler import LAS_HANDLER


class Segment:
    """
    Utility class for processing and running segmentation code
    """

    # TODO: Implement run segmentation predict code in this class instead of worker.py

    def __init__(
        self,
        debug: bool = True,
        silent: bool = False,
    ):
        self.debug = debug
        self.silent = silent
        self.las_handler = LAS_HANDLER()

    def translate_segmentation_to_original_center(
        self, original_las_path: str, segmented_las_path: str
    ) -> bool:
        """Overwrite segmentation file with re-centered points, back
        to their original location.

        Parameters
        ----------
        original_las_path : str
            Path to .las or .laz file of original pointcloud
            before centering around the origin
        segmented_las_path : str
            Path to .las or .laz file of segmentation results
            after centering around the origin

        Returns
        -------
        bool
            True if overwriting segmentation file succeeded.
            Otherwise False.
        """
        # Read original and segmented files
        points_orig, _, _ = self.las_handler.read_laz(original_las_path)
        points_seg, colors_seg, classes_seg = self.las_handler.read_laz(
            segmented_las_path
        )

        # Re-center the coordinates
        points_center_orig = np.mean(points_orig, axis=0)
        points_seg = (points_seg + points_center_orig).astype(np.float64)

        # Overwrite segmented file
        return self.las_handler.save(
            segmented_las_path, points_seg, colors_seg, classes_seg
        )
