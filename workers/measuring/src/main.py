import os
from os.path import join, basename, splitext, exists
import argparse
from typing import List, Tuple, Any
import numpy as np
import open3d as o3d
import matplotlib.pyplot as plt
import sys
from skimage import exposure
import pandas as pd
from sklearn.cluster import MeanShift, DBSCAN
import pyvista as pv

o3d.utility.set_verbosity_level(o3d.utility.VerbosityLevel.Error)

from las_handler import LAS_HANDLER


class Measure:
    """
    This class runs the measurement on all the seedlings in the
    given fellowbox
    """

    def __init__(
        self,
        file_path: str,
        output_dir: str,
        debug: bool = True,
        silent: bool = False,
    ):
        """
        __init__ Initialization of a Measure object

        Parameters
        ----------
        file_path : str
            las file path
        debug : bool, optional
            debug mode, by default True
        silent : bool, optional
            silent mode, by default False
        """
        self._debug = debug
        self._silent = silent
        self.file_path = file_path
        self.output_dir = output_dir
        self.las_handler = LAS_HANDLER()
        self.stem_class = 1
        self.branch_class = 2
        self.leaf_class = 3

        self.points, self.colors, self.segmented_classes = self.las_handler.read_laz(
            self.file_path
        )
        # 1. Read file
        self.points = np.array(self.points, dtype=np.float64)
        self.colors = np.array(self.colors, dtype=np.float64)
        if self.segmented_classes is not None:
            self.segmented_classes = np.array(self.segmented_classes, dtype=np.int16)
        else:
            print(f"classification is not present")

        self.pcd = o3d.geometry.PointCloud()
        self.pcd.points = o3d.utility.Vector3dVector(self.points)
        self.pcd.colors = o3d.utility.Vector3dVector(self.colors / 100000)

    def noise_filtering(
        self, points: np.ndarray, colors: np.ndarray, classes: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        noise_filtering - a simple clustering based noise filtering

        Parameters
        ----------
        points : input points
        color: input matching colors
        classes: input matching classes (stem, branch, leaf, etc)

        Returns
        -------
        clean_points, clean_colors, clean_classes
            points and labels with the noise class obtained from the
            DBSCAN clustering removed.
        """

        # Convert to PointCloud object
        pcd = self.np_to_pcd(points)

        # Clusters points to find instances
        labels = self.find_clusters(pcd, eps=0.005, min_points=300)

        # Remove noise clusters that is class -1
        clean_points = points[labels >= 0]
        clean_colors = colors[labels >= 0]
        clean_classes = classes[labels >= 0]

        return clean_points, clean_colors, clean_classes

    def distance(self, point1: List[float], point2: List[float]) -> float:
        """
        distance between 2 points

        Parameters
        ----------
        point1 : List[float]
            3D point 1
        point2 : List[float]
            3D point 2

        Returns
        -------
        float
            distance between the 2 points
        """
        return np.sqrt(
            (point1[0] - point2[0]) ** 2
            + (point1[1] - point2[1]) ** 2
            + (point1[2] - point2[2]) ** 2
        )

    def measure_leaf_area(
        self, alpha: float = 0.01, smooth_niter: int = 1
    ) -> Tuple[Any, Any, Any]:
        """
        measure_leaf_area

        Parameters
        ----------
        alpha : float, optional
            alpha value for mesh creation, by default 0.03
        smooth_niter : int, optional
            number of smoothing iterations for mesh, by default 1

        Returns
        -------
        Tuple[Any]
            leaf area, and dimensions of the leaf
        """

        print(f"Measuring leaf area of: {self.file_path}")

        ##### COMMENTED BECAUSE OF NEWER 3D FILTERING #####

        # # 1. Filter noise from biggest cluster
        # filtered, filtered_colors, filtered_classes = self.noise_filtering(
        #     self.points, self.colors, self.segmented_classes
        # )

        # # Filter segmentation noise from X- and Y-axis
        # leaf_clusters = self.dbscan_clustering(filtered[:, 0], filtered[:, 1], eps=0.025)

        # biggest_cluster = np.argmax(np.bincount(leaf_clusters))
        # filtered = filtered[leaf_clusters == biggest_cluster]
        # filtered_colors = filtered_colors[leaf_clusters == biggest_cluster]
        # filtered_classes = filtered_classes[leaf_clusters == biggest_cluster]

        # # 1. Filter noise from biggest cluster
        # leaf_filtered, leaf_filtered_colors, filtered_classes = self.noise_filtering(
        #     filtered, filtered_colors, filtered_classes
        # )

        # # filter on XZ as well
        # # leaf_clusters = self.dbscan_clustering(filtered[:, 0], filtered[:, 2], eps=0.025)

        # # biggest_cluster = np.argmax(np.bincount(leaf_clusters))
        # # filtered = filtered[leaf_clusters == biggest_cluster]
        # # filtered_colors = filtered_colors[leaf_clusters == biggest_cluster]
        # # filtered_classes = filtered_classes[leaf_clusters == biggest_cluster]

        # # leaf_filtered = filtered
        # # leaf_filtered_colors = filtered_colors

        # # filter on the leaf class
        # # leaf_filtered = filtered[filtered_classes == self.leaf_class]
        # # leaf_filtered_colors = filtered_colors[filtered_classes == self.leaf_class]

        # if len(leaf_filtered) != 0:

        #     pcl = o3d.geometry.PointCloud()
        #     pcl.points = o3d.utility.Vector3dVector(leaf_filtered)

        #######################################################################

        points_included = self.find_3D_clusters(self.points, eps=0.02)
        filtered = self.points[points_included]
        filtered_colors = self.colors[points_included]
        filtered_classes = self.segmented_classes[points_included]

        # filter on the leaf class
        leaf_filtered = filtered[filtered_classes == self.leaf_class]
        leaf_filtered_colors = filtered_colors[filtered_classes == self.leaf_class]

        points_included = [
            False if self.segmented_classes[i] != self.leaf_class else index
            for i, index in enumerate(points_included)
        ]
        points_excluded = [not elem for elem in points_included]

        # get points 2 cm around leafs
        length = len(leaf_filtered)
        diff = 1
        count = 0

        while diff > 0 and count < 5:
            count += 1

            add_points, add_points_colours = self.points_around_leaf(
                leaf_filtered,
                self.points[points_excluded],
                self.colors[points_excluded],
                0.02,
            )
            leaf_filtered = np.append(leaf_filtered, add_points, axis=0)
            leaf_filtered_colors = np.append(
                leaf_filtered_colors, add_points_colours, axis=0
            )

            diff = len(leaf_filtered) - length
            length = len(leaf_filtered)

        if len(leaf_filtered) != 0:
            pcl = o3d.geometry.PointCloud()
            pcl.points = o3d.utility.Vector3dVector(leaf_filtered)
            # o3d.visualization.draw_geometries([pcl])
            # convert points to mesh

            # alpha mesh creation
            mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_alpha_shape(
                pcl, alpha
            )
            # smooth the mesh a little
            mesh = mesh.filter_smooth_simple(number_of_iterations=smooth_niter)
            # calculate the area of the the created leaf mesh
            leaf_area = mesh.get_surface_area()

            # get dimensions of the mesh
            oriented_bb = mesh.get_oriented_bounding_box()
            bb_points = oriented_bb.get_box_points()
            # calculate dimensions of the oriented box - vector 01, 02, & 03
            l = self.distance(bb_points[0], bb_points[1])
            w = self.distance(bb_points[0], bb_points[2])
            h = self.distance(bb_points[0], bb_points[3])

            # TODO: Finish Geodesic distance calculation
            # First create a very smooth mesh
            # mesh_smooth = o3d.geometry.TriangleMesh.create_from_point_cloud_alpha_shape(
            #     pcl, 0.05
            # )
            # mesh_smooth = mesh_smooth.filter_smooth_simple(number_of_iterations=20)
            # mesh_smooth_path = join(
            #     self.output_dir,
            #     f"{splitext(basename(self.file_path))[0]}_mesh_smooth.ply",
            # )
            # o3d.io.write_triangle_mesh(mesh_smooth_path, mesh_smooth)
            # TODO: Find points on mesh to calculate geodesic distance
            # point_a = ...
            # point_b = ...
            # length = self.geodesic_distance_between_points(mesh_smooth_path, point_a, point_b)
            # point_a = ...
            # point_b = ...
            # width = self.geodesic_distance_between_points(mesh_smooth_path, point_a, point_b)

            if self._debug:
                outpath = join(
                    self.output_dir,
                    f"{splitext(basename(self.file_path))[0]}_leafarea_mesh.ply",
                )
                o3d.io.write_triangle_mesh(outpath, mesh)
                outpath_nr = join(
                    self.output_dir,
                    f"{splitext(basename(self.file_path))[0]}_leaf_noiseremoved.laz",
                )
                self.las_handler.save(
                    outpath_nr, leaf_filtered, colors=leaf_filtered_colors
                )

            return (
                np.round(leaf_area * 1000000, 1),
                np.round(np.sort([l, w, h])[1] * 1000, 1),
                np.round(np.sort([l, w, h])[2] * 1000, 1),
            )
        else:
            print("Leaves not present/segmented in this cloud. Returning zeros.")
            return 0, 0, 0

    def points_around_leaf(self, leaf_points, points, colors, cm):
        """Includes the points around the leaf points, to get a more complete point cloud
        to analyse leaf area on.

        Parameters
        ----------
        leaf_points : List[List[float]]
            The leaf points
        points : List[List[float]]
            The points to potentially include.
        colors : List[List[float]]
            The colours of the points to potentially include.
        cm : float
            How much cm around the leaf points do we want to include

        Returns
        -------
        filtered, filtered_colours: List[List[float]], List[List[float]]
            The point cloud to analyse, with its corresponding colours
        """

        lx = leaf_points[:, 0]
        ly = leaf_points[:, 1]
        lz = leaf_points[:, 2]

        inds = []
        for idx, p in enumerate(points):

            min_x = p[0] - cm
            max_x = p[0] + cm
            min_y = p[1] - cm
            max_y = p[1] + cm
            min_z = p[2] - cm
            max_z = p[2] + cm

            logical_x = np.logical_and(lx > min_x, lx < max_x)
            logical_xy = np.logical_and(ly[logical_x] > min_y, ly[logical_x] < max_y)
            logical_xyz = np.logical_and(
                lz[logical_x][logical_xy] > min_z, lz[logical_x][logical_xy] < max_z
            ).any()

            inds.append(logical_xyz)

        return points[inds], colors[inds]

    def measure_head_circumference(
        self,
    ) -> Tuple[float, List[float]]:
        """Measure head circumference of a tomato plant

        Returns
        -------
        Tuple[float, List[float]]
            - Cirfumference of the head (in mm), defaults to -1 if
              circumference couldn't be calculated
            - List of diameter estimations of all slices
        """
        self._print(f"Measuring head circumference of: {self.file_path}")

        if self.stem_class not in self.segmented_classes:
            print(
                f"No stem points found, therefore couldn't calculate the head circumference!"
            )
            return -1, []

        # select the stem class only
        if self.stem_class in np.unique(self.segmented_classes):
            stem_points = self.points[self.segmented_classes == self.stem_class]
            stem_colors = self.colors[self.segmented_classes == self.stem_class]
        else:
            stem_points = self.points
            stem_colors = self.colors

        # 1. Filter noise
        # Filter segmentation noise from X- and Z-axis
        stem_clusters = self.dbscan_clustering(
            stem_points[:, 0], stem_points[:, 2], eps=0.01
        )
        # Make sure noise clusters have positive index
        stem_clusters = [
            c if c != -1 else len(np.unique(stem_clusters)) for c in stem_clusters
        ]
        biggest_cluster = np.argmax(np.bincount(stem_clusters))
        stem_points_filtered = stem_points[stem_clusters == biggest_cluster]
        stem_colors_filtered = stem_colors[stem_clusters == biggest_cluster]
        if self._debug:
            outpath = join(
                self.output_dir,
                f"{splitext(basename(self.file_path))[0]}_filtered.laz",
            )
            self.las_handler.save(
                outpath,
                stem_points,
                colors=stem_colors,
                classification=np.array(stem_clusters, dtype=np.int32),
            )

        # 2. Get 10 slices (1 cm thick) of points between 15-25 cm below the top of the plant
        points_y = stem_points_filtered[:, 1]  # type: ignore
        top_of_the_plant = self.get_top_of_the_plant(stem_points_filtered)
        measure_start_point = top_of_the_plant + 0.15

        diameters = []
        for i in range(10):
            # Determine min and max Y for this slice
            max_y = measure_start_point + (0.01 * i) + 0.005
            min_y = measure_start_point + (0.01 * i) - 0.005

            # Find points in entire pointcloud for this slice
            ind_all = np.logical_and(self.points[:, 1] < max_y, self.points[:, 1] > min_y)
            slice_points_all = self.points[ind_all]
            slice_colors_all = self.colors[ind_all]

            # Find stem points for this slice
            ind_stem = np.logical_and(points_y < max_y, points_y > min_y)
            slice_points_stem = stem_points_filtered[ind_stem]
            slice_colors_stem = stem_colors_filtered[ind_stem]

            # Skip if there are no stem points
            if len(slice_points_stem) <= 10:
                continue

            # Do additional clustering on stem points in slice
            # and find largest cluster
            stem_clusters = self.dbscan_clustering(
                slice_points_stem[:, 0], slice_points_stem[:, 2], eps=0.01
            )
            stem_clusters = [
                c if c != -1 else len(np.unique(stem_clusters)) for c in stem_clusters
            ]
            biggest_cluster = np.argmax(np.bincount(stem_clusters))
            slice_points_stem = slice_points_stem[stem_clusters == biggest_cluster]
            slice_colors_stem = slice_colors_stem[stem_clusters == biggest_cluster]
            slice_center = np.mean(slice_points_stem, axis=0)

            # Include points from entire pointcloud that are within 1 cm from center of the stem slice
            new_stem_point_indices = [
                True if self.distance(point, slice_center) < 0.01 else False
                for point in slice_points_all
            ]
            new_stem_points = slice_points_all[new_stem_point_indices]
            new_stem_colors = slice_colors_all[new_stem_point_indices]

            # Merge points
            slice_points_stem = np.vstack((slice_points_stem, new_stem_points))
            slice_colors_stem = np.vstack((slice_colors_stem, new_stem_colors))

            # Calculate diameter
            if not self.check_branching_stem(slice_points_stem):
                diameter = self.calculate_diameter(
                    slice_points_stem[:, 0], slice_points_stem[:, 2]
                )
                diameters.append(diameter)

                # Save slice pointcloud
                if self._debug:
                    outpath = join(
                        self.output_dir,
                        f"{splitext(basename(self.file_path))[0]}_slice_{i}.laz",
                    )
                    self.las_handler.save(
                        outpath, slice_points_stem, colors=slice_colors_stem
                    )
            else:
                print(
                    "This slice does not contain any points, or is too close to branching off"
                )

        outliers_removed = self.remove_stem_diameter_outliers(diameters)
        # take mean again
        diameter_final = np.mean(outliers_removed)
        circumference = self.calculate_circumference(diameter_final)

        return circumference, diameters

    def _print(self, *args, **kwargs):
        """Prints inputted arguments if silent mode is off."""
        if not self._silent:
            print(*args, **kwargs)

    def check_branching_stem(self, slice_points) -> bool:
        """This function checks if a slice of stem points is next to a branch, by checking
        whether any points of the branch class are within 0.5cm euclidian distance of the slice.

        Only when more than 5% of the slice points are close to a branch, the slice is classified
        as 'next to branch' (or True), and skipped in the head circumference calculation.

        Parameters
        ----------
        slice_points : List[List[float]]
            List of stem cells (x, y and z coordinates) of the slice to be tested

        Returns
        -------
        boolean
            True if slice is next to branch (< 0.5cm away), False if not
        """

        # select the stem class only
        if self.branch_class in np.unique(self.segmented_classes):
            leaf_points = self.points[self.segmented_classes == self.branch_class]
        else:
            return False

        stem_x = slice_points[:, 0]
        stem_y = slice_points[:, 1]
        stem_z = slice_points[:, 2]

        for leaf_point in leaf_points:
            ind_euclidian = (
                np.sqrt(
                    (stem_x - leaf_point[0]) ** 2
                    + (stem_y - leaf_point[1]) ** 2
                    + (stem_z - leaf_point[2]) ** 2
                )
                < 0.005
            )

        # return true of more than 5% of the stem points are next to a branch
        if 100 * len([i for i in ind_euclidian if i]) / len(slice_points) > 5:
            return True
        else:
            return False

    @staticmethod
    def calculate_diameter(points_x: np.ndarray, points_y: np.ndarray) -> float:
        """Calculate the diameter of a set of 2D points

        Parameters
        ----------
        points_x : np.ndarray
            1 dimensional list of points over the X-axis
        points_y : np.ndarray
            1 dimensional list of points over the Y-axis

        Returns
        -------
        float
            Diameter of the points
        """
        points_x = points_x - np.min(points_x)
        points_y = points_y - np.min(points_y)

        # project onto diagonals for more robust estimate
        theta = 0.25 * np.pi
        points_xy = points_x * np.cos(theta) - points_y * np.sin(theta)
        points_yx = points_x * np.sin(theta) + points_y * np.cos(theta)

        distance_x = np.max(points_x)
        distance_y = np.max(points_y)
        distance_xy = np.max(points_xy) - np.min(points_xy)
        distance_yx = np.max(points_yx) - np.min(points_yx)

        # take the second largest direction for robustness
        diameter = np.sort([distance_x, distance_y, distance_yx, distance_xy])[2]

        return float(diameter)

    @staticmethod
    def calculate_circumference(diameter: float) -> float:
        """Calculate the circumference of a plant based on
        the diameter of the stem

        Parameters
        ----------
        diameter : float
            Diameter of the stem in meters

        Returns
        -------
        float
            Circumference of the stem in millimeters
            rounded to 1 decimal.
        """
        return np.round(np.pi * diameter * 1000, 1)

    @staticmethod
    def remove_stem_diameter_outliers(diameters: List[float]) -> List[float]:
        """Remove stem diameter outliers
        1. all diameters smaller than 5mm and larger than 20 mm are removed
        2. Remove all remaining diameter measurements 1 sigma away from median

        Parameters
        ----------
        diameters : List[float]
            List of stem diameter estimations in meters

        Returns
        -------
        List[float]
            List of stem diameters without outliers in meters
        """
        # Remove all tiny and very large stem diameters
        diameters = [d for d in diameters if d > 0.005 and d < 0.02]

        # outlier removal above 1 sigma and then averaging the diameters to get the final estimate
        median, std = np.median(diameters), np.std(diameters)
        low, up = median - std, median + std
        diameters = [d for d in diameters if d > low and d < up]

        return diameters

    @staticmethod
    def fit_line(points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Determine line that fits a set of 3D points
        using Singular Value Decomposition approach.

        Parameters
        ----------
        points : np.ndarray
            Set of 3D points, must be an array of
            shape [n, 3].

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            Returns two numpy arrays of shape [3]:
            - line vector
            - point on the fitted line
        """
        points_mean = points.mean(axis=0)

        # Do an SVD on the mean-centered data.
        _, _, vv = np.linalg.svd(points - points_mean)
        line_vector = vv[0]

        return line_vector, points_mean

    @staticmethod
    def rotation_matrix_align_vectors(
        vector_a: np.ndarray, vector_b: np.ndarray
    ) -> np.ndarray:
        """Calculate rotation matrix that aligns one vector
        to another.

        Parameters
        ----------
        vector_a : np.ndarray
            3D vector
        vector_b : np.ndarray
            3D vector

        Returns
        -------
        np.ndarray
            Rotation matrix that rotates vector A to vector B
        """
        a = vector_a  # short alias to avoid coding
        b = vector_b  # short alias to avoid coding

        cross_product = np.cross(a, b)
        axis = cross_product / np.linalg.norm(cross_product)
        sin_a = np.linalg.norm(np.cross(a, b))
        cos_a = np.dot(a, b)
        one_minus_cos_a = 1.0 - cos_a

        result = np.array(
            [
                [
                    (axis[0] * axis[0] * one_minus_cos_a) + cos_a,
                    (axis[1] * axis[0] * one_minus_cos_a) - (sin_a * axis[2]),
                    (axis[2] * axis[0] * one_minus_cos_a) + (sin_a * axis[1]),
                ],
                [
                    (axis[0] * axis[1] * one_minus_cos_a) + (sin_a * axis[2]),
                    (axis[1] * axis[1] * one_minus_cos_a) + cos_a,
                    (axis[2] * axis[1] * one_minus_cos_a) - (sin_a * axis[0]),
                ],
                [
                    (axis[0] * axis[2] * one_minus_cos_a) - (sin_a * axis[1]),
                    (axis[1] * axis[2] * one_minus_cos_a) + (sin_a * axis[0]),
                    (axis[2] * axis[2] * one_minus_cos_a) + cos_a,
                ],
            ],
            dtype=np.float,
        )
        return result

    @staticmethod
    def geodesic_distance_between_points(
        mesh_filepath: str, point_a: List[float], point_b: List[float]
    ) -> float:
        """Calculate the geodesic distance between two points
        on a mesh (.ply file)

        Parameters
        ----------
        mesh_filepath : str
            Path to a .ply file containing a triangulated mesh.
        point_a : List[float]
            List of 3 numbers XYZ
        point_b : List[float]
            List of 3 numbers XYZ

        Returns
        -------
        float
            Distance along the triangles of the mesh between
            point_a and point_b
        """
        assert len(point_a) == 3
        assert len(point_b) == 3

        mesh = pv.read(mesh_filepath)
        A = mesh.find_closest_point((point_a[0], point_a[1], point_a[2]))
        B = mesh.find_closest_point((point_b[0], point_b[1], point_b[2]))

        distance = mesh.geodesic_distance(A, B)
        return distance

    def get_top_of_the_plant(
        self, stem_points: np.ndarray, line_thickness: float = 0.05
    ) -> float:
        """Find the top of the plant by fitting a line through the stem points
        and taking the highest point from the points that intersect the line

        Parameters
        ----------
        stem_points : np.ndarray
            3D points of the stem of the plant, array shape: [n, 3]
        line_thickness : float, optional
            Thickness of the line that is used to find
            intersections, by default 0.05

        Returns
        -------
        float
            The smallest y coordinate from the intersected points
        """
        # Fit line through stem points
        stem_line_vector, stem_line_point = self.fit_line(stem_points)

        # Calculate rotation from fitted line to X-axis
        rotate_to_axis = np.array([1, 0, 0])
        R = self.rotation_matrix_align_vectors(stem_line_vector, rotate_to_axis)

        # Rotate point cloud
        rotated_points = (self.points - stem_line_point) @ R.T

        # Find points that intersect the line
        line_intersection_indices_y = np.logical_and(
            rotated_points[:, 1] < line_thickness, rotated_points[:, 1] > -line_thickness
        )
        line_intersection_indices_z = np.logical_and(
            rotated_points[:, 2] < line_thickness, rotated_points[:, 2] > -line_thickness
        )
        line_intersection_indices = np.logical_and(
            line_intersection_indices_y, line_intersection_indices_z
        )
        line_intersection_points = self.points[line_intersection_indices]

        if self._debug:
            line_intersection_colors = self.colors[line_intersection_indices]
            outpath = join(
                self.output_dir,
                f"{splitext(basename(self.file_path))[0]}_stem_line_intersections.laz",
            )
            self.las_handler.save(
                outpath, line_intersection_points, colors=line_intersection_colors
            )

        # Determine top of the plant
        top_of_the_plant = np.min(line_intersection_points[:, 1])
        return top_of_the_plant

    def np_to_pcd(self, points: np.ndarray) -> o3d.geometry.PointCloud:
        """Converts a numpy points array to an o3d.geomtery.Pointcloud() object.

        Parameters:
        -----------
        points: np.array(n, 3)
            array of points in xyz space

        Returns:
        --------

        pcd: o3d.geometry.PointCloud
            Open3D pointcloud object
        """

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)

        return pcd

    def show(self):
        """Displays the loaded point cloud using the Open3D visualizer"""
        o3d.visualization.draw_geometries([self.pcd])

    def show_points(self, points):
        """Displays the passed points using the Open3D visualizer

        Parameters:
        -----------
        points: np.array(n, 3)
            array of points in xyz space
        """
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        o3d.visualization.draw_geometries([pcd])

    def show_pcd(self, pcd, save_img=False, name_append=""):
        """Displays the passed points using the Open3D visualizer

        Parameters:
        -----------
        points: np.array(n, 3)
            array of points in xyz space
        """
        o3d.visualization.draw_geometries([pcd])

        if save_img:
            vis = o3d.visualization.Visualizer()
            vis.create_window(
                visible=False
            )  # works for me with False, on some systems needs to be true
            vis.add_geometry(pcd)
            vis.update_geometry(pcd)
            vis.poll_events()
            vis.update_renderer()

            # Extract original filename from self.file_path, add to out directory and optionally append name_append
            save_name = f"{self.output_dir}/{self.file_path.split('/')[-1].split('.laz')[0]}_{name_append}.png"
            vis.capture_screen_image(save_name)
            vis.destroy_window()

    def measure_tomato_setting(
        self, eps=0.002, min_points=10
    ) -> Tuple[int, o3d.geometry.PointCloud]:
        """Measures the amount of tomatoes in the point cloud.

        Parameters:
        -----------
        eps: float
            distance to neighbors in a cluster
        min_points: int
            minimum number of points required to form a cluster

        Returns:
        --------
        Tuple[num_clusters, tomato_pcd]
            num_clusters: int
                Total number of found clusters
            tomato_pcd: o3d.geometry.PointCloud
                The point cloud with clustered labels as colors.
        """

        # Select only tomato points
        indx = np.where(self.segmented_classes == 5.0)
        tomato_points = self.points[indx]

        # Check if any tomato points are present
        if len(tomato_points) > 0:

            # Convert to PointCloud object
            tomato_pcd = self.np_to_pcd(tomato_points)

            # Clusters points to find instances
            labels = self.find_clusters(tomato_pcd, eps, min_points)

            # Count number of clusters
            max_label = labels.max()
            num_clusters = max_label + 1
            print(f"Found: {num_clusters} tomato clusters")

            # Add colors to pointcloud to visualize found clusters
            colors = plt.get_cmap("tab20")(labels / (max_label if max_label > 0 else 1))
            colors[labels < 0] = 0
            tomato_pcd.colors = o3d.utility.Vector3dVector(colors[:, :3])

        else:
            print("No points with tomato class present in file, skipping tomato setting")
            num_clusters = 0
            tomato_pcd = o3d.geometry.PointCloud()

        return num_clusters, tomato_pcd

    def measure_flower_setting(
        self, eps=0.002, min_points=10
    ) -> Tuple[int, o3d.geometry.PointCloud]:
        """Measures the amount of flowers in the point cloud.

        Parameters:
        -----------
        eps: float
            distance to neighbors in a cluster
        min_points: int
            minimum number of points required to form a cluster

        Returns:
        --------
        Tuple[num_clusters, flower_pcd]
            num_clusters: int
                Total number of found clusters
            tomato_pcd: o3d.geometry.PointCloud
                The point cloud with clustereed labels as colors.
        """

        # Select only flower points
        indx = np.where(self.segmented_classes == 4.0)
        flower_points = self.points[indx]

        # Check if any flower points are present
        if len(flower_points) > 0:

            # Convert to PointCloud object
            flower_pcd = self.np_to_pcd(flower_points)

            # Clusters points to find instances
            labels = self.find_clusters(flower_pcd, eps, min_points)

            # Count number of clusters
            max_label = labels.max()
            num_clusters = max_label + 1
            print(f"Found: {num_clusters} flower clusters")

            # Add colors to pointcloud to visualize found clusters
            colors = plt.get_cmap("tab20")(labels / (max_label if max_label > 0 else 1))
            colors[labels < 0] = 0
            flower_pcd.colors = o3d.utility.Vector3dVector(colors[:, :3])
        else:
            print("No points with flower class present in file, skipping flower setting")
            num_clusters = 0
            flower_pcd = o3d.geometry.PointCloud()

        return num_clusters, flower_pcd

    def find_clusters(self, pcd, eps, min_points):
        """Uses the DBSCAN algorithm to find clusters within a point cloud.

        Parameters:
        -----------
        eps: float
            distance to neighbors in a cluster
        min_points: int
            minimum number of points required to form a cluster

        Returns
        labels: open3d.utility.IntVector
            Cluster labels
        """
        with o3d.utility.VerbosityContextManager(o3d.utility.VerbosityLevel.Debug) as cm:
            labels = np.array(
                pcd.cluster_dbscan(eps=eps, min_points=min_points, print_progress=True)
            )
        return labels

    def find_3D_clusters(self, points, eps):
        """Uses the DBSCAN algorithm to find clusters within a point cloud.

        Parameters:
        -----------
        points: List[List[float]]
            The points to find the 3D clusters off
        colors: List[List[float]]
            The colours of the points that are clustered. Filtering will apply to
            the colours as well as the points.
        eps: float
            distance to neighbors in a cluster

        Returns
        indices: List[bool]
            List, length of the number of points, with whether they are part of the biggest cluster or not
        """
        # Convert to PointCloud object
        pcd = self.np_to_pcd(points)
        with o3d.utility.VerbosityContextManager(o3d.utility.VerbosityLevel.Debug) as cm:
            labels = np.array(
                pcd.cluster_dbscan(eps=eps, min_points=200, print_progress=True)
            )

        # Remove noise clusters that is class -1
        clean_labels = labels[labels >= 0]

        # Only keep the biggest cluster
        biggest_cluster = np.argmax(np.bincount(clean_labels))
        indices = labels == biggest_cluster

        return indices

    def mean_shift_clustering(self, x: List[float], y: List[float]) -> List[int]:
        """Apply mean-shift clustering to 2 dimensional data

        Parameters
        ----------
        x : List[float]
            List of numbers of the first dimension (X) with
            n elements
        y : List[float]
            List of numbers of the second dimension (Y) with
            n elements

        Returns
        -------
        List[int]
            list with n elements of cluster indices.
            For example: [1,1,1,2,1,2,2,2].
        """
        mean_shift_model = MeanShift(n_jobs=-1)
        data = np.transpose(np.array([x, y], dtype=np.float))
        return mean_shift_model.fit_predict(data)

    def dbscan_clustering(
        self, x: List[float], y: List[float], eps: float = 0.05, min_samples: int = 9
    ) -> List[int]:
        """Apply dbscan clustering to 2 dimensional data

        Parameters
        ----------
        x : List[float]
            List of numbers of the first dimension (X) with
            n elements
        y : List[float]
            List of numbers of the second dimension (Y) with
            n elements
        eps : float, optional
            Epsilon parameter of DBSCAN algorithm, by default 0.05
        min_samples : int, optional
            Minimum number of points in a cluster, by default 9

        Returns
        -------
        List[int]
            list with n elements of cluster indices.
            For example: [1,1,1,2,1,2,2,2].
        """
        dbscan_model = DBSCAN(eps=eps, min_samples=min_samples)
        data = np.transpose(np.array([x, y], dtype=np.float))
        return dbscan_model.fit_predict(data)

    def extract_color(
        self, apply_normalization: bool = False, color_method: str = "gimp-wb"
    ) -> Any:
        """Extracts a normalized color from the stem."""
        print(f"Color.shape: {self.colors.shape}, points.shape: {self.points.shape}")

        # Normalize colors
        if apply_normalization:
            self.colors = normalize_color(self.colors, color_method)

        # Select colors belonging to the stem
        indx = np.where(self.segmented_classes == 1.0)
        stem_colors = self.colors[indx]

        if len(stem_colors) > 0:

            # Calculate averages
            average_R = np.mean(stem_colors[:, 0])
            average_G = np.mean(stem_colors[:, 1])
            average_B = np.mean(stem_colors[:, 2])

            if self._debug:
                print(
                    "Debug = True, so changing colors in point cloud to average of stem..."
                )

                # Make whole point cloud average color of the stem (for debugging)
                self.colors[:, 0] = average_R
                self.colors[:, 1] = average_G
                self.colors[:, 2] = average_B

                # Save results
                outpath = join(
                    self.output_dir,
                    f"{splitext(basename(self.file_path))[0]}_color-extracted.las",
                )
                self.las_handler.save(
                    outpath,
                    points=self.points,
                    colors=self.colors,
                    classification=self.segmented_classes,
                )

            # Return average stem color
            return average_R, average_G, average_B
        else:
            print("No points with stem class present in file, skipping discoloration")
            return 0, 0, 0


def normalize_color(colors, method="greyworld"):
    """Normalizes color values to a standard space using the specified method

    Parameters:
    -----------

    colors: np.array(n, 3)
        array of RGB colors
    method: str
        Method of color normalization. Options: [greyworld, gimp-wb, histogram-matching]
        Scale Monitor RGB
        Scale XYZ
        Von Kries
        Scaling camera RGB

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
        _, ref_colors, _ = LAS_HANDLER().read_laz(reference_path)
        ref_colors = np.array(ref_colors, dtype=np.float64)

        colors = exposure.match_histograms(colors, ref_colors, channel_axis=1)

    return colors


def whitebalance_channel(channel, percentile=0.05):
    min, max = (
        np.percentile(channel, percentile),
        np.percentile(channel, 100.0 - percentile),
    )
    channel = np.uint8(np.clip((channel - min) * 255.0 / (max - min), 0, 255))
    return channel


def get_lasfiles_in_folder(path: str) -> List[str]:
    """Finds all .las files in a directory and returns the filenames.

    Parameters:
    -----------
    path: str
        path to the folder to extract files from

    Returns:
    --------
    las_files: List[str]
        List of found .las files
    """
    las_files = []

    for f in os.listdir(path):
        if f.endswith(".las") and os.path.isfile(join(path, f)):
            las_files.append(f)

    return las_files


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Required arguments:
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        metavar="PATH",
        help="Input .las file.",
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
    parser.add_argument("-s", "--silent", action="store_true", help="Turn on silent mode")
    parser.add_argument("--merge-plant", action="store_true", help="Save images")
    parser.add_argument("--save_img", action="store_true", help="Save images")
    parser.add_argument(
        "--color_method",
        type=str,
        help="Type of color normalization to apply, options: [gimp-wb, grayworld]",
    )
    parser.add_argument(
        "--process_folder",
        action="store_true",
        help="Iterate over all files in folder and process all files",
    )
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    if args.process_folder:
        filenames = get_lasfiles_in_folder(args.input)

        df_list = []

        for i, filename in enumerate(filenames):

            print(f"Processing {i+1}/{len(filenames)}: {filename}")

            m = Measure(
                os.path.join(args.input, filename),
                args.output,
                debug=True,
                silent=args.silent,
            )
            avg_R, avg_G, avg_B = m.extract_color()

            # Measure tomato setting and visualize results
            tomato_setting, tomato_pcd = m.measure_tomato_setting()

            # Measure flower setting and visualize results
            flower_setting, flower_pcd = m.measure_flower_setting()

            # Measure head circumference
            circum, _ = m.measure_head_circumference()
            leaf_area, length, width = m.measure_leaf_area()

            # add rc_visard, path, plant and date to dict (from file name)
            file_split = filename.split("_")
            rc_idx = file_split.index("rc-visard")
            rc_id = file_split[rc_idx + 1]
            path_idx = file_split.index("pad")
            path_number = file_split[path_idx + 1]
            plant_idx = file_split.index("plant")
            plant_number = file_split[plant_idx + 1]
            date = file_split[rc_idx + 2]

            dict = {
                "rc_visard_id": rc_id,
                "path_number": path_number,
                "plant_number": plant_number,
                "date": date,
                "tomato_setting": tomato_setting,
                "flower_setting": flower_setting,
                "circumference": circum,
                "leaf_area": leaf_area,
                "length": length,
                "width": width,
                "stem_color_R": avg_R,
                "stem_color_B": avg_B,
                "stem_color_G": avg_G,
            }
            df_list.append(dict)
        df = pd.DataFrame(df_list)
        df.to_csv(join(args.output, f"results_predictions.csv"))

    else:

        m = Measure(
            args.input,
            args.output,
            debug=True,
            silent=args.silent,
        )

        # Measure tomato setting and visualize results
        tomato_setting, tomato_pcd = m.measure_tomato_setting()
        # m.show_pcd(tomato_pcd, args.save_img, name_append="tomatos")

        # Measure flower setting and visualize results
        flower_setting, flower_pcd = m.measure_flower_setting()
        # m.show_pcd(flower_pcd, args.save_img, name_append="flowers")

        # Measure head circumference
        circum, _ = m.measure_head_circumference()
        leaf_area, length, width = m.measure_leaf_area()

        # Measure average color and visualize result
        avg_R, avg_G, avg_B = m.extract_color(
            apply_normalization=False, color_method=args.color_method
        )
        m.pcd.colors = o3d.utility.Vector3dVector(m.colors)
        m.show()

        dict = {
            "tomato_setting": tomato_setting,
            "flower_setting": flower_setting,
            "circumference": circum,
            "leaf_area": leaf_area,
            "length": length,
            "width": width,
            "stem_color_R": avg_R,
            "stem_color_B": avg_B,
            "stem_color_G": avg_G,
        }
        df = pd.DataFrame(dict, index=[0])
        df.to_csv(join(args.output, f"{basename(args.output)}.csv"))

        print(f"Circumference: {circum} mm")
        print(f"Leaf area: {leaf_area} squaremm")
        print(f"Leaf length: {length} mm")
        print(f"Leaf width: {width} mm")
        print(f"Flower setting: {flower_setting} flowers")
        print(f"Tomato setting: {tomato_setting} tomatoes")
        print(f"Average color of stem: {avg_R * 255.0}, {avg_G * 255.0}, {avg_B * 255.0}")
