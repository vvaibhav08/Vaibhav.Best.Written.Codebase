from cProfile import label
import pytest
import math
import numpy as np
from typing import List
import pylas
import os

from app.main import Measure
from app.las_handler import LAS_HANDLER


def test_create_laz():
    test_points = np.array([[0.0, 1.0, 2.0], [3.0, 4.0, 5.0], [6.0, 7.0, 8.0]])
    test_colors = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    test_classification = np.array([0, 1, 2])

    outfile = LAS_HANDLER.create(
        test_points, colors=test_colors, classification=test_classification
    )

    assert isinstance(
        outfile, pylas.lasdatas.las12.LasData
    ), f"outfile: {outfile}, {type(outfile)}"
    # Check if outfile content is correct
    assert all(outfile.x == test_points[:, 0])
    assert all(outfile.y == test_points[:, 1])
    assert all(outfile.z == test_points[:, 2])
    assert all(outfile.classification == test_classification)
    assert all(outfile.red == test_colors[:, 0])
    assert all(outfile.green == test_colors[:, 1])
    assert all(outfile.blue == test_colors[:, 2])


def test_read_laz():
    path = "/tests/files/p5kop_stem_test_circumference.laz"
    points, colors, labels = LAS_HANDLER.read_laz(path)

    # Check types of output variables
    assert isinstance(points, List), f"points: {points}, {type(points)}"
    assert isinstance(colors, List), f"colors: {colors}, {type(colors)}"
    if labels is None:
        print(f"colors: {labels}, {type(labels)}")
    assert isinstance(
        points[0][0], np.float16
    ), f"points[0][0]: {points[0][0]}, {type(points[0][0])}"
    assert isinstance(
        colors[0][0], np.float16
    ), f"colors[0][0]: {colors[0][0]}, {type(colors[0][0])}"
    points_np = np.array(points)
    colors_np = np.array(colors)
    assert points_np.shape[1] == 3, f"points.shape: {points_np.shape}"
    assert colors_np.shape[1] == 3, f"points.shape: {colors_np.shape}"


def test_save_laz():
    test_points = np.array([[0.0, 1.0, 2.0], [3.0, 4.0, 5.0], [6.0, 7.0, 8.0]])
    test_colors = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])

    tmp_out_path = "/tmp/test_save_laz.las"
    result = LAS_HANDLER.save(tmp_out_path, test_points, colors=test_colors)
    assert isinstance(result, bool), f"result: {result}, {type(result)}"
    assert result
    assert os.path.exists(tmp_out_path)

    # Check if saved file contains correct data
    points, colors, _ = LAS_HANDLER.read_laz(tmp_out_path)
    points = np.array(points)
    colors = np.array(colors)
    assert all(points[:, 0] == test_points[:, 0])
    assert all(points[:, 1] == test_points[:, 1])
    assert all(points[:, 2] == test_points[:, 2])

    assert all(colors[:, 0] == test_colors[:, 0])
    assert all(colors[:, 1] == test_colors[:, 1])
    assert all(colors[:, 2] == test_colors[:, 2])


def test_calculate_diameter():
    # Generate 100 points on circle with radius of 0.01
    r = 0.01
    n = 100
    points = np.array(
        [
            [math.cos(2 * math.pi / n * x) * r, math.sin(2 * math.pi / n * x) * r]
            for x in range(0, n + 1)
        ]
    )
    points_x = points[:, 0]
    points_y = points[:, 1]

    diameter = Measure.calculate_diameter(points_x, points_y)
    assert isinstance(diameter, float), f"diameter: {diameter}, {type(diameter)}"
    assert diameter == r * 2, f"diameter: {diameter}, actual_diameter: {r*2}"


def test_measuring_circumference_tomato_head():
    m = Measure(
        "/tests/files/p5kop_stem_test_circumference.laz", "/tmp", debug=True, silent=False
    )
    measure_dist = 0.05
    measure_from = "top"
    circumference = m.measure_head_circumference(measure_dist, measure_from)
    assert isinstance(
        circumference, float
    ), f"circumference: {circumference}, {type(circumference)}"
    assert 200 > circumference > 0.01


def test_measuring_leafarea():
    m = Measure("/tests/files/test_blad.las", "/tmp", debug=True, silent=False)
    a, l, w = m.measure_leaf_area()
    assert isinstance(a, float), f"leaf area: {a}, {type(a)}"
    assert a > 0
    assert isinstance(l, float), f"width: {l}, {type(l)}"
    assert l > 0
    assert isinstance(w, float), f"width: {w}, {type(w)}"
    assert w > 0
