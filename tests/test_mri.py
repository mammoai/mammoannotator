import os
import shutil

import numpy as np
import pytest
from mammoannotator.mri import (
    CroppedImage,
    RawImage,
    ensure_folder_exists,
    list_dirs,
    list_files,
)
from PIL import Image

# Images for patient_A/exam_A
image_paths = [
    "data/mri/patient_A/exam_A/test_image_l_Ax.jpeg",
    "data/mri/patient_A/exam_A/test_image_r_Ax.jpeg",
    "data/mri/patient_A/exam_A/test_image_l_Sag.jpeg",
    "data/mri/patient_A/exam_A/test_image_r_Sag.jpeg",
]

# Tests for Utils


@pytest.fixture
def base_path(TESTS_PATH):
    return os.path.join(TESTS_PATH, "data/utils/filesystem")


@pytest.mark.unit_test
def test_list_dirs(base_path):
    expected = [os.path.join(base_path, x) for x in ["A", "B"]]
    behaviour = list_dirs(base_path)
    assert behaviour == expected


@pytest.mark.unit_test
def test_list_files(base_path):
    expected = [os.path.join(base_path, "C.txt")]
    behaviour = list_files(base_path, "txt")
    assert behaviour == expected


@pytest.mark.unit_test
def test_ensure_folder_exists(base_path):
    folder = os.path.join(base_path, "temp_D")
    try:
        ensure_folder_exists(folder)
        assert "temp_D" in os.listdir(base_path)
    except:
        raise KeyError
    finally:
        os.rmdir(folder)


@pytest.fixture
def test_im_1(TESTS_PATH):
    im_path = os.path.join(TESTS_PATH, "data/mri/test_image_1.png")
    return Image.open(im_path)


@pytest.fixture
def test_im_2(TESTS_PATH):
    im_path = os.path.join(TESTS_PATH, "data/mri/patient_A/exam_A/test_image_l_Ax.jpeg")
    return Image.open(im_path)


# Tests for RawImage


@pytest.mark.unit_test
def test_measure(test_im_1, test_im_2):
    assert RawImage.measure(test_im_1) == (30, 20, 30 / 20)
    assert RawImage.measure(test_im_2) == (400, 800, 400 / 800)


@pytest.mark.unit_test
@pytest.mark.parametrize(
    "filename,expected",
    [
        ("xxxxx_l_Sag.jpeg", ("left", "sagittal")),
        ("xxxxx_l_Ax.jpeg", ("left", "axial")),
        ("a_B_xxxxx_r_Sag.jpeg", ("right", "sagittal")),
        ("yy_xxxxx_r_Ax.jpeg", ("right", "axial")),
    ],
)
def test_parse_file_name(filename, expected):
    assert RawImage.parse_file_name(filename) == expected


@pytest.mark.parametrize(
    "img_path,expected",
    [(path, loc) for path, loc in zip(image_paths, [425, 483, 395, 361])],
)
def test_find_white_start(TESTS_PATH, img_path, expected):
    im = Image.open(os.path.join(TESTS_PATH, img_path))
    image = np.array(im)
    white_start = RawImage.find_white_start(image)
    assert expected - 10 < white_start < expected + 10


@pytest.mark.unit_test
@pytest.mark.parametrize("img_path", image_paths)
def test_from_path(TESTS_PATH, img_path):
    full_path = os.path.join(TESTS_PATH, img_path)
    # Just checking that it does not break
    raw_image = RawImage.from_path(full_path)


# Tests for CroppedImage
@pytest.mark.unit_test
@pytest.mark.parametrize("img_path", image_paths)
def test_get_crop_folder_path(img_path):
    raw_image = RawImage.from_path(img_path)
    expected = os.path.join(os.path.split(img_path)[0], "crops")
    try:
        assert CroppedImage.get_crops_folder_path(raw_image) == expected
        assert os.path.exists(expected)
    finally:
        shutil.rmtree(expected)


@pytest.mark.unit_test
@pytest.mark.parametrize(
    "img_path,expected",
    [
        (p, e)
        for p, e in zip(image_paths, [(400, 800), (400, 800), (373, 773), (339, 739)])
    ],
)
def test_get_crop_positions(img_path, expected):
    raw_image = RawImage.from_path(img_path)
    assert CroppedImage.get_crop_positions(raw_image) == expected


@pytest.fixture
def mini_image():
    image = [
        [0, 1, 0],
        [0, 1, 0],
        [0, 1, 1],
    ]
    return np.array(image)


@pytest.mark.unit_test
@pytest.mark.parametrize(
    "kwargs,expected",
    [
        (
            {"rotate": 0, "h_flip": True, "v_flip": True},
            [
                [1, 1, 0],
                [0, 1, 0],
                [0, 1, 0],
            ],
        ),
        (
            {"rotate": 1, "h_flip": False, "v_flip": False},
            [
                [0, 0, 1],
                [1, 1, 1],
                [0, 0, 0],
            ],
        ),
        (
            {"rotate": 1, "h_flip": False, "v_flip": False},
            [
                [0, 0, 1],
                [1, 1, 1],
                [0, 0, 0],
            ],
        ),
    ],
)
def test_rotate_and_flip(mini_image, kwargs, expected):
    assert (
        CroppedImage.rotate_and_flip(mini_image, **kwargs) == np.array(expected)
    ).all()


@pytest.mark.parametrize("img_path", image_paths)
def test_from_raw_image(TESTS_PATH, img_path):
    crops_path = os.path.split(os.path.join(TESTS_PATH, img_path))[0] + "/crops"
    raw_image = RawImage.from_path(img_path)
    try:
        cropped_image = CroppedImage.from_raw_image(raw_image)
        assert cropped_image.image.shape == (
            CroppedImage.side_size,
            CroppedImage.side_size,
        )
    finally:
        shutil.rmtree(crops_path)


@pytest.mark.unit_test
def test_get_crop_details(TESTS_PATH):
    full_path = os.path.join(TESTS_PATH, image_paths[2])
    raw_image = RawImage.from_path(full_path)
    crops_path = os.path.split(full_path)[0] + "/crops"
    try:
        cropped_image = CroppedImage.from_raw_image(raw_image)
        d = cropped_image.get_crop_details()
        assert d["h_flip"] == False
        assert d["v_flip"] == True
        assert d["rotation"] == 3
        assert d["crop_start"] == 373
        assert d["crop_end"] == 773
        assert d["original_width"] == 270
        assert d["original_height"] == 800
    finally:
        shutil.rmtree(crops_path)
