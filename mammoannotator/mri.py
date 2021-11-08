import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Dict, List, Tuple, Union

import numpy as np
from PIL import Image


def list_dirs(path: str) -> List[str]:
    """List all dirs inside path"""
    dirs = [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))]
    return sorted([os.path.join(path, d) for d in dirs])


def list_files(folder_path: str, extension: str) -> List[str]:
    """get paths of files ending with <extension> in a folder"""
    filenames = [f for f in os.listdir(folder_path) if f.endswith(extension)]
    return sorted([os.path.join(folder_path, f) for f in filenames])


@dataclass
class RawImage:
    image_path: str
    laterality: str
    view: str
    image: np.array
    white_start: int  # from top to down, where is the
    # first row with a value higher than white_threshold

    white_threshold = 50

    @classmethod
    def from_path(cls, path: str):
        basename = os.path.basename(path)
        lat, view = cls.parse_file_name(basename)
        with Image.open(path) as im:
            image = np.array(im)
        assert image.shape[0] > image.shape[1], f"horizontal image: {path}"
        white_start = cls.find_white_start(image)
        return cls(
            laterality=lat,
            view=view,
            image_path=path,
            image=image,
            white_start=white_start,
        )

    @classmethod
    def find_white_start(cls, image):
        row_max = np.max(image, axis=-1)
        return np.argwhere(row_max > cls.white_threshold)[0][0]

    @staticmethod
    def parse_file_name(fn: str) -> Tuple[str, str]:
        root, extension = os.path.splitext(fn)
        _, _, _, _, _, _, laterality, view = root.split("_")
        if laterality == "l":
            laterality = "left"
        elif laterality == "r":
            laterality = "right"
        else:
            raise Exception(f"Laterality is '{laterality}' instead of 'l' or 'r'")

        if view == "Sag":
            view = "sagittal"
        elif view == "Ax":
            view = "axial"
        else:
            raise Exception(f"View is '{view}' instead of 'Sag' or 'Ax'")
        return laterality, view


@dataclass
class CroppedImage:
    laterality: str
    view: str
    crop_start: int
    crop_end: int
    rotation: int
    flip: bool
    image: np.array
    image_path: str

    margin = 20  # pixels

    @classmethod
    def from_raw_image(cls, raw_image: RawImage):
        image = raw_image.image
        crop_start = max(raw_image.white_start - cls.margin, 0)
        crop_start = min(
            crop_start, image.shape[0] - image.shape[1]
        )  # latest start to be able to get a square
        crop_end = crop_start + image.shape[1]
        image = image[crop_start:crop_end, :]
        rotate, flip = 0, False
        if raw_image.laterality == "right":
            rotate = 90 // 90  # one time counterclockwise
            image = np.rot90(image, k=rotate)
            if raw_image.view == "sagittal":
                flip = True
                image = np.flip(image, axis=0)
        else:
            rotate = 270 // 90  # three times counterclockwise
            image = np.rot90(image, k=rotate)

        im = Image.fromarray(image)
        path, fn = os.path.split(raw_image.image_path)
        im_name, extension = os.path.splitext(fn)
        crops_path = os.path.join(path, "crops")
        if not os.path.exists(os.path.join(path, "crops")):
            os.mkdir(crops_path)
        full_path = os.path.join(crops_path, f"{im_name}_crop{extension}")
        im.save(full_path)

        return cls(
            image=image,
            crop_start=crop_start,
            crop_end=crop_end,
            laterality=raw_image.laterality,
            view=raw_image.view,
            image_path=full_path,
            rotation=rotate,
            flip=flip,
        )

    def get_crop_details(self):
        return dict(
            crop_start=int(self.crop_start),
            crop_end=int(self.crop_end),
            rotation=int(self.rotation),
            flip=self.flip,
        )


@dataclass
class MRITask:
    patient_id: str
    study_id: str
    assessment: str
    image_path: str
    crops: Dict[Tuple[str, str], CroppedImage]
    crop_details: Dict[str, Dict[str, Union[int, bool]]]
    assessment: str

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

    def set_assessment_from_csv(self, df):
        row = df[
            (df["anonExaminationStudyId"] == self.study_id)
            & (df["anonPatientId"] == self.patient_id)
        ]
        if len(row) == 0:
            print(
                f"could not find row in assessment csv for study: {self.study_id} and patient: {self.patient_id}"
            )
            self.assessment = "Not found in csv"
            return
        elif len(row) > 1:
            print(
                f"more than one row in assessment csv for study: {self.study_id} and patient: {self.patient_id}"
            )
            self.assessment = "More than one found in csv"
            return
        assessment = row["ReportTextText"].values[0]
        assert isinstance(assessment, str), f"Assessment is not str: {assessment}"
        self.assessment = assessment

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
        for i in raw_shapes[1:]:
            assert np.all(
                i == raw_shapes[0]
            ), f"Image with different shape: {study_path}"
        n_px = raw_shapes[0][1]

        # build a new image with all four scans
        full_image = np.zeros([2 * n_px, 2 * n_px], dtype=np.uint8)
        full_image[0:n_px, 0:n_px] = cls.get_img(frames, "right", "sagittal", n_px)
        full_image[0:n_px, n_px:] = cls.get_img(frames, "left", "sagittal", n_px)
        full_image[n_px:, 0:n_px] = cls.get_img(frames, "right", "axial", n_px)
        full_image[n_px:, n_px:] = cls.get_img(frames, "left", "axial", n_px)

        # get details
        patient_id, study_id = study_path.split(os.sep)[-2:]
        assesment = ""
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
            assessment=assesment,
            image_path=fp,
            crops=Dict[Tuple[str, str], CroppedImage],
            crop_details=crop_details,
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
        return task

    def as_dict(self):
        doc = asdict(self)
        doc.pop("crops")
        return doc

    def make_url(self, server_root: str, url: str):
        rel_path = os.path.relpath(self.image_path, server_root)
        img_url = f"{url}/{rel_path}"
        self.image_path = img_url

