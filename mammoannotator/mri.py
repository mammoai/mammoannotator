import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Dict, List, Tuple, Union

import numpy as np
from PIL import Image

import mammoannotator


def list_dirs(path: str) -> List[str]:
    """List all dirs inside path"""
    dirs = [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))]
    return sorted([os.path.join(path, d) for d in dirs])


def list_files(folder_path: str, extension: str) -> List[str]:
    """get paths of files with <extension> in a folder"""
    filenames = []
    extension = f".{extension}" if not extension.startswith(".") else extension
    for f in os.listdir(folder_path):
        if os.path.splitext(f)[1] == extension:
            filenames.append(f)
    return sorted([os.path.join(folder_path, f) for f in filenames])


def ensure_folder_exists(folder_path: str):
    if not os.path.exists(folder_path):
        os.mkdir(folder_path)


@dataclass
class RawImage:
    image_path: str
    width: int  # pixels
    height: int  # pixels
    ratio: float  # w/h if h is 0, then ratio is 0.
    laterality: str
    view: str
    image: np.array
    white_start: int  # from top to down, where is the
    # first row with a value higher than white_threshold
    white_threshold = 50

    @staticmethod
    def measure(im: Image):
        im = np.array(im)
        h, w = im.shape
        ratio = w / h if h != 0 else 0
        return w, h, ratio

    @classmethod
    def from_path(cls, path: str):
        assert os.path.splitext(path)[1].lower() in [
            ".jpeg",
            ".jpg",
            ".png",
        ], f"The extension of image {path} must be jpg, jpeg or png"
        basename = os.path.basename(path)
        lat, view = cls.parse_file_name(basename)
        with Image.open(path) as im:
            w, h, ratio = cls.measure(im)
            image = np.array(im)

        # sanity checks
        assert image.shape[0] > image.shape[1], f"Horizontal image: {path}"
        assert (
            0.1 < ratio < 0.9
        ), f"Ratio for image {path} is too high or too low. Ratio: {ratio}"

        white_start = cls.find_white_start(image)
        return cls(
            laterality=lat,
            view=view,
            image_path=path,
            image=image,
            white_start=white_start,
            width=w,
            height=h,
            ratio=ratio,
        )

    @classmethod
    def find_white_start(cls, image: np.array):
        """get the vertical position where the average intensity is higher than cls.margin for the first time (top to bottom)"""
        w = image.shape[-1]
        # use only the central strip bc there are annotations on the corner sometimes
        c_start, c_end = 2 * w // 5, 3 * w // 3
        row_max = np.mean(image[:, c_start:c_end], axis=-1)
        return np.argwhere(row_max > cls.white_threshold)[0][0]

    @staticmethod
    def parse_file_name(fn: str) -> Tuple[str, str]:
        root, _ = os.path.splitext(fn)
        parts = root.split("_")

        laterality = parts[-2]
        if laterality == "l":
            laterality = "left"
        elif laterality == "r":
            laterality = "right"
        else:
            raise Exception(
                f"For {fn}, laterality is '{laterality}' instead of 'l' or 'r'"
            )

        view = parts[-1]
        if view == "Sag":
            view = "sagittal"
        elif view == "Ax":
            view = "axial"
        else:
            raise Exception(f"For {fn}, view is '{view}' instead of 'Sag' or 'Ax'")
        return laterality, view


@dataclass
class CroppedImage:
    laterality: str
    view: str
    crop_start: int
    crop_end: int
    rotation: int
    h_flip: bool
    v_flip: bool
    image: np.array
    image_path: str
    original_width: int
    original_height: int

    # Class configurations. Sorry for hard coding!
    side_size = 360  # size of the output square
    margin = 0.0277  # compared to the original height (~20px when 720px)

    @classmethod
    def get_crop_positions(cls, raw_image: RawImage):
        """obtain the vertical positions to start and end the crop"""
        margin_px = round(raw_image.height * cls.margin)
        # never start in a negative position
        start = max(raw_image.white_start - margin_px, 0)
        # latest start to be able to crop a "square"
        # (square after it is resized and considering it will have a 0.5 aspect ratio)
        start = min(start, raw_image.height // 2)
        end = start + raw_image.height // 2
        return start, end

    @staticmethod
    def mod_rules(laterality: str, view: str):
        """explicitly set the rules for modifying each combination of laterality and view.
        it is expected that they are done in order (first rotate, then h_flip, then v_flip)
        returns a dict with keys
            rotate: <int> number of counterclockwise rotations of 90 degrees,
            h_flip: <bool> if the image should be flipped horizontally (d -> b)
            v_flip: <bool> if the image should be flipped vertically (p -> b)
        """
        R = "right"
        L = "left"
        S = "sagittal"
        A = "axial"
        _1 = True
        _0 = False
        default_rules = {
            (R, S): {"rotate": 1, "h_flip": _0, "v_flip": _0},
            (R, A): {"rotate": 1, "h_flip": _0, "v_flip": _0},
            (L, S): {"rotate": 3, "h_flip": _0, "v_flip": _1},
            (L, A): {"rotate": 3, "h_flip": _0, "v_flip": _0},
        }
        return default_rules[(laterality, view)]

    @staticmethod
    def rotate_and_flip(image: np.array, rotate: int, h_flip: bool, v_flip: bool):
        """rotates, and flips the image"""
        
        if rotate > 0:
            image = np.rot90(image, k=rotate)
        if h_flip:
            image = np.flip(image, axis=1)
        if v_flip:
            image = np.flip(image, axis=0)
        return image

    @staticmethod
    def get_crops_folder_path(raw_image: RawImage):
        path, _ = os.path.split(raw_image.image_path)
        crops_path = os.path.join(path, "crops")
        ensure_folder_exists(crops_path)
        return crops_path

    @staticmethod
    def get_image_path(raw_image: RawImage):
        crops_path = CroppedImage.get_crops_folder_path(raw_image)
        _, fn = os.path.split(raw_image.image_path)
        im_name, extension = os.path.splitext(fn)
        image_filename = f"{im_name}_crop{extension}"
        full_image_path = os.path.join(crops_path, image_filename)
        return full_image_path

    @classmethod
    def from_raw_image(cls, raw_image: RawImage):
        image = raw_image.image
        # Crop image
        crop_start, crop_end = cls.get_crop_positions(raw_image)
        image = image[crop_start:crop_end, :]
        # Rotate and flip
        mods = CroppedImage.mod_rules(raw_image.laterality, raw_image.view)
        image = cls.rotate_and_flip(image, **mods)
        rotate, h_flip, v_flip = mods.values()
        # Resize to get a square of constant size even if the ratio was wrong
        im = Image.fromarray(image)
        im = im.resize([cls.side_size, cls.side_size])
        image = np.array(im)
        # Save the newly created image
        full_path = cls.get_image_path(raw_image)
        im.save(full_path)
        # Create a class
        return cls(
            image=image,
            crop_start=crop_start,
            crop_end=crop_end,
            laterality=raw_image.laterality,
            view=raw_image.view,
            image_path=full_path,
            rotation=rotate,
            h_flip=h_flip,
            v_flip=v_flip,
            original_width=raw_image.width,
            original_height=raw_image.height,
        )

    def get_crop_details(self):
        return dict(
            crop_start=int(self.crop_start),
            crop_end=int(self.crop_end),
            rotation=int(self.rotation),
            h_flip=self.h_flip,
            v_flip=self.v_flip,
            original_width=int(self.original_width),
            original_height=int(self.original_height),
        )


@dataclass
class MRITask:
    patient_id: str
    study_id: str
    image_path: str
    crops: Dict[Tuple[str, str], CroppedImage]
    crop_details: Dict[str, Dict[str, Union[int, bool]]]
    mammoannotator_version: str
    assessment: str = "" # set with csv
    examination_timestamp: str = "" #set with csv

    @classmethod
    def from_root_folder(cls, root_path: str) -> List["MRITask"]:
        patient_paths = list_dirs(root_path)
        for patient_path in patient_paths:
            for task in cls.from_patient_folder(patient_path):
                yield task

    @classmethod
    def from_patient_folder(cls, patient_path: str) -> List["MRITask"]:
        """get a list of tasks by patient folder"""
        study_paths = list_dirs(patient_path)
        for study_path in study_paths:
            yield cls.from_study_folder(study_path)

    @staticmethod
    def get_img(
        crops: Dict[Tuple[str, str], CroppedImage], lat: str, view: str, n_px: int
    ) -> np.array:
        crop = crops.get((lat, view), None)
        crop = (
            crop.image if crop is not None else np.zeros([n_px, n_px], dtype=np.uint8)
        )
        return crop

    @classmethod
    def from_study_folder(cls, study_path: str) -> "MRITask":
        """One task per study folder"""
        frames = dict()
        raw_shapes = []
        image_paths = list_files(study_path, ".jpeg")

        # check that there is at least one image
        if len(image_paths) == 0:
            logging.error(f"no images in folder {study_path}")
            return None

        # get the images in a Dict[Tuple[str,str]:CroppedImage]
        for image_path in image_paths:
            raw_image = RawImage.from_path(image_path)
            raw_shapes.append(raw_image.image.shape)
            cropped_image = CroppedImage.from_raw_image(raw_image)
            frames[(cropped_image.laterality, cropped_image.view)] = cropped_image

        # Define the size of the square
        # for i in raw_shapes[1:]:
        #     assert np.all(
        #         i == raw_shapes[0]
        #     ), f"Image with different shape: {study_path}"
        n_px = CroppedImage.side_size

        # build a new image with all four scans
        full_image = np.zeros([2 * n_px, 2 * n_px], dtype=np.uint8)
        full_image[0:n_px, 0:n_px] = cls.get_img(frames, "right", "sagittal", n_px)
        full_image[0:n_px, n_px:] = cls.get_img(frames, "left", "sagittal", n_px)
        full_image[n_px:, 0:n_px] = cls.get_img(frames, "right", "axial", n_px)
        full_image[n_px:, n_px:] = cls.get_img(frames, "left", "axial", n_px)

        # get details
        patient_id, study_id = study_path.split(os.sep)[-2:]
        crop_details = {
            f"{lat}_{view}": cropped_image.get_crop_details()
            for (lat, view), cropped_image in frames.items()
        }

        # store the new image
        im = Image.fromarray(full_image)
        crops_path = os.path.join(study_path, "crops")
        fp = os.path.join(crops_path, "all_views.jpeg")
        if not os.path.exists(crops_path):
            os.mkdir(crops_path)
        im.save(fp)

        return cls(
            patient_id=patient_id,
            study_id=study_id,
            image_path=fp,
            crops=Dict[Tuple[str, str], CroppedImage],
            crop_details=crop_details,
            mammoannotator_version=mammoannotator.__version__,
        )

    @classmethod
    def from_csv_row(cls, root_path, row: dict):
        """row is a dict that has 'anonPatientId' and 'anonExaminationStudyId'"""
        study_path = os.path.join(
            root_path, row["anonPatientId"], row["anonExaminationStudyId"]
        )
        assert os.path.exists(study_path), f"Study path not found: {study_path}"
        task = cls.from_study_folder(study_path)
        task.assessment = row["ReportTextText"]
        task.examination_timestamp = row['ExaminationDate']
        return task

    def as_dict(self):
        doc = asdict(self)
        doc.pop("crops")
        return doc

    def make_url(self, server_root: str, url: str):
        rel_path = os.path.relpath(self.image_path, server_root)
        img_url = f"{url}/{rel_path}"
        self.image_path = img_url
