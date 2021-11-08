import csv
import json
import os
import re
import sys
import zipfile
from csv import DictReader, DictWriter
from datetime import datetime
from shutil import rmtree
from typing import Any, Dict, List, Tuple, Type

import numpy as np
from PIL import Image
from tqdm.auto import tqdm

from mammoannotator.labelstudio_api import LabelStudioAPI
from mammoannotator.mri import MRITask, list_files


def create_dir_if_missing(path):
    if not os.path.exists(path):
        os.mkdir(path)


def merge_images(image_paths, output_path) -> str:
    """
    image_paths are expected to be binary images. Creates the union of all the
    images and stores it in output_path.
    """
    images = []
    for path in image_paths:
        with Image.open(path) as im:
            images.append(np.array(im, dtype=bool))
    merged_array = np.logical_or(*images).astype(np.uint8) * 255
    merged_image = Image.fromarray(merged_array)
    merged_image.save(output_path)


def slice_arr_by_lat_view(arr, lat_view, width: int):
    if lat_view == "right_sagittal":
        return arr[:width, :width]
    elif lat_view == "left_sagittal":
        return arr[:width, width:]
    elif lat_view == "right_axial":
        return arr[width:, :width]
    elif lat_view == "left_axial":
        return arr[width:, width:]
    else:
        raise TypeError(f"Unknown {lat_view=}")


def reverse_crop(
    im_arr: np.array, crop_details: dict
) -> Dict[str, Tuple[Image.Image, int]]:
    """Return the recovered image and the number of annotated pixels per
    lat_view. If the lat_view annotation has no annotations, nothing is added
    for that image."""
    width = 360
    height = 720  # TODO: add this variable to crop details and read it from there
    recovered_images = {}
    for lat_view, details in crop_details.items():
        lat_view_arr = slice_arr_by_lat_view(im_arr, lat_view, width)
        lat_view_arr[lat_view_arr < 0] = 255
        annotated_pixels = np.count_nonzero(lat_view_arr)
        if annotated_pixels == 0:
            continue  # no annotations on this lat_view -> skip
        # reverse flip
        if details["flip"]:
            lat_view_arr = np.flip(lat_view_arr, axis=0)
        # reverse rot90
        if details["rotation"] != 0:
            lat_view_arr = np.rot90(lat_view_arr, k=-details["rotation"])
        new_arr = np.zeros(shape=[height, width], dtype=np.uint8)

        new_arr[details["crop_start"] : details["crop_end"], :] = lat_view_arr
        new_im = Image.fromarray(new_arr)
        recovered_images[lat_view] = (new_im, annotated_pixels)
    return recovered_images


class TaskDAO:
    def __init__(self, connector: LabelStudioAPI):
        self.connector = connector

    def create_task(self, task: MRITask, project_id, img_server_url, img_server_root):
        task.make_url(img_server_root, img_server_url)
        task_dict = json.dumps(task.as_dict())
        answer = self.connector.create_task(data=task_dict, project=project_id)
        task_id = answer["id"]
        return task_id

    @staticmethod
    def _parse_image_filename(filename: str) -> Tuple[int, int, str, str]:
        # TODO: convert this script to maintainable classes and functions
        """Parse the name of an image that was downloaded from LS.

        Args:
            filename (str): something like 'task-76-annotation-37-by-example@mail.com-labels-4 nonmass-0.png'

        Returns:
            Tuple[int, int, str, str]: task_id, annotation_id, by, label_str
        """
        pattern = r"task-(?P<task>\d+)-annotation-(?P<annotation>\d+)-by-(?P<email>[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)-labels-(?P<label>[\sa-zA-Z0-9_.+-]+)-[0-9+].png"
        result = re.search(pattern, filename)
        if result is None:
            raise ValueError(f"Invalid filename: {filename}")
        result = (
            int(result.group("task")),
            int(result.group("annotation")),
            result.group("email"),
            result.group("label"),
        )
        result
        return result

    def get_task_annotations(
        self, project_id: int, task_id: int, study_path: int
    ) -> List[Dict[str, Any]]:
        """Exports a single task's annotations to the folder it is specified.

        Returns:
            A list of dicts with one entry per image with the following keys:
                'project_id': The specified project_id.
                'task_id': The task that was exported.
                'annotation_id': the id of the annotation that produced the
                 image.
                'view': one of ['all_views', 'right_sagittal', 'left_sagittal',
                 'right_axial', 'left_axial'].
                'label' name of the label for that image.
                'annotated_pixels': count of annotated pixels.
                'image_path': full path to the image.
        Raises:
            TypeError: Unknown file type.
            IndexError: annotation label with no associated images.
        """
        output_list = []

        task_json = self.connector.export_tasks_and_annotations(
            project_id,
            export_type="JSON_MIN",
            download_all_tasks=False,
            download_resources=False,
            task_ids=[task_id],
            local_folder=None,
        )
        assert (
            len(task_json) > 0
        ), f"No annotations found for project {project_id} and task {task_id}"
        task_file = self.connector.export_tasks_and_annotations(
            project_id,
            export_type="BRUSH_TO_PNG",
            download_all_tasks=False,
            download_resources=False,
            task_ids=[task_id],
            local_folder=study_path,
        )
        temp_folder = os.path.join(study_path, "temp")
        try:
            if task_file.endswith(".zip"):  # more than one label
                create_dir_if_missing(temp_folder)
                with zipfile.ZipFile(task_file, "r") as zip_file:
                    zip_file.extractall(temp_folder)
                os.remove(task_file)
                all_images = list_files(temp_folder, ".png")
            elif task_file.endswith(".png"):  # a single label
                _, filename = os.path.split(task_file)
                img_path = os.path.join(temp_folder, filename)
                os.rename(task_file, img_path)
                all_images = [img_path]
            else:
                raise TypeError(f"Unkown extension of file: {task_file}")
            all_images
            # Run quality checks
            ## No annotations in the edge.
            ## Empty Pixels that are fully surrounded by annotatated pixels.
            ## Annotations in black areas.
            # Merge labels that have the same annotation and title
            annotations = {
                annotation_dict["annotation_id"]: {  # as obtained from LS
                    "task_id": annotation_dict["id"],
                    "anntoation_id": annotation_dict["annotation_id"],
                    "crop_details": annotation_dict["crop_details"],
                    "study_path": study_path,
                    "labels": {
                        label_dict["brushlabels"][0]: []
                        for label_dict in annotation_dict["labels"]
                    },
                }
                for annotation_dict in task_json
            }
            ## Group images by annotation-label
            for image in all_images:
                temp_folder, filename = os.path.split(image)
                task_id, ann_id, by, label = self._parse_image_filename(filename)
                annotations[ann_id]["labels"][label].append(image)

            annotations_folder = os.path.join(study_path, "annotations")
            create_dir_if_missing(annotations_folder)

            ## Merge and save in the correct location
            for a_id, annotation in annotations.items():
                annotation_folder = os.path.join(annotations_folder, str(a_id))
                create_dir_if_missing(annotation_folder)
                annot_all_views_folder = os.path.join(annotation_folder, "all_views")
                create_dir_if_missing(annot_all_views_folder)
                for label, images in annotation["labels"].items():
                    l = len(images)
                    safe_label = label.replace(" ", "_")
                    new_name = f"p-{project_id}-t-{task_id}-a-{a_id}-all_views-{safe_label}.png"
                    new_filepath = os.path.join(annot_all_views_folder, new_name)
                    if l == 1:  # Rename and move file to folder
                        os.rename(images[0], new_filepath)
                    elif l > 1:
                        merge_images(images, new_filepath)
                    else:
                        raise IndexError(
                            f"Found {l} images in annotation{a_id} - label {label}"
                        )
                    with Image.open(new_filepath) as im:
                        im_array = np.array(im)
                        output_list.append(
                            dict(
                                project_id=project_id,
                                task_id=task_id,
                                annotation_id=a_id,
                                view="all_views",
                                label=safe_label,
                                annotated_pixels=np.count_nonzero(im_array),
                                image_path=new_filepath,
                            )
                        )
                        # Recover original shape by reversing the crop
                        recovered = reverse_crop(im_array, annotation["crop_details"])
                    for lat_view, (im, pixel_count) in recovered.items():
                        lat_view_folder = os.path.join(annotation_folder, lat_view)
                        create_dir_if_missing(lat_view_folder)
                        image_name = f"p-{project_id}-t-{task_id}-a-{a_id}-{lat_view}-{safe_label}.png"
                        image_path = os.path.join(lat_view_folder, image_name)
                        im.save(image_path)
                        output_list.append(
                            dict(
                                project_id=project_id,
                                task_id=task_id,
                                annotation_id=a_id,
                                view=lat_view,
                                label=safe_label,
                                annotated_pixels=pixel_count,
                                image_path=image_path,
                            )
                        )
        finally:
            rmtree(temp_folder)
        return output_list


class ProjectDAO:
    def __init__(self, connector: LabelStudioAPI):
        self.connector = connector

    def create_project(
        self,
        title: str,
        description: str,
        interface_config_path: str,
        instruction_path: str,
    ):

        # read the labeling interface config
        with open(interface_config_path) as file:
            config = "".join([l for l in file])
        # read the labeling interface config
        with open(instruction_path) as file:
            instructions = "".join([l for l in file])

        project = self.connector.create_project(
            title=title,
            description=description,
            label_config=config,
            expert_instruction=instructions,
            created_by={"first_name": "Admin", "last_name": "", "email": ""},
            show_instruction=True,
            show_skip_button=True,
            enable_empty_annotation=False,
        )
        return project["id"]

    def create_mri_project_from_csv(
        self,
        csv_path,
        interface_config_path: str,
        instruction_path: str,
        root_path: str,
        img_server_url: str,
    ):
        """Create a Label Studio project and create tasks based on a CSV file.

        Args:
            csv_path (str): A csv that contains at least the following columns:
             'anonPatientId', 'anonExaminationStudyId', 'ReportTextText'.
            interface_config_path (str): Path to XML formatted config.
            instruction_path (str): Path to HTML formatted instructions.
            root_path (str): Path where the patients' folders exist. This is
             also the root of the img server
            img_server_url (str): base url where the images will be found
        """
        csv.field_size_limit(sys.maxsize)
        csv_parent, csv_basename = os.path.split(csv_path)
        today = datetime.now().strftime("%Y-%m-%d")
        title = f"MRI {today}"
        description = f"Based on {csv_basename}"
        task_dicts = []
        # preventive read first
        with open(csv_path, newline="") as file:
            reader = DictReader(file)
            fields = reader.fieldnames
            assert "anonPatientId" in fields
            assert "anonExaminationStudyId" in fields
            assert "ReportTextText" in fields
            for row in reader:
                try:
                    assert os.path.exists(
                        os.path.join(
                            root_path, row["anonPatientId"], row["anonExaminationStudyId"]
                        )
                    ), f"{row['anonPatientId']}/{row['anonExaminationStudyId']} does not exist"
                    task_dicts.append(row)
                except:
                    print(f"{row['anonPatientId']}/{row['anonExaminationStudyId']} does not exist")
        # create project
        print(f"Creating {title} {description}")
        project_id = self.create_project(
            title, description, interface_config_path, instruction_path
        )
        print(f"Successfullly created project {project_id}")
        # now send all tasks to labelstudio
        task_dao = TaskDAO(self.connector)
        new_csv_path = os.path.join(csv_parent, f"{project_id}-MRI-{today}.csv")
        out_fieldnames = fields + [
            "ls_project_id",
            "ls_task_id",
            "left_sagittal",
            "right_sagittal",
            "left_axial",
            "right_axial",
        ]
        with open(new_csv_path, "w") as file:
            writer = DictWriter(file, out_fieldnames)
            writer.writeheader()
            for task_dict in tqdm(task_dicts, desc="Creating tasks"):
                try:
                    task = MRITask.from_csv_row(root_path, task_dict)
                    task_id = task_dao.create_task(
                        task, project_id, img_server_url, root_path
                    )
                    # Add information to output dict
                    task_dict["ls_project_id"] = project_id
                    task_dict["ls_task_id"] = task_id
                    task_dict["left_sagittal"] = task.crop_details.get(
                        "left_sagittal", None
                    )
                    task_dict["right_sagittal"] = task.crop_details.get(
                        "right_sagittal", None
                    )
                    task_dict["left_axial"] = task.crop_details.get("left_axial", None)
                    task_dict["right_axial"] = task.crop_details.get("right_axial", None)
                    writer.writerow(task_dict)
                except:
                    print(f"Failed to create task for {task_dict['anonPatientId']}/{task_dict['anonExaminationStudyId']}")
                    print(f"{task_dict}")
    def export_tasks_from_csv(self, tasks_csv_path: str, images_csv_path: str):
        root_path, csv_name = os.path.split(tasks_csv_path)
        task_dao = TaskDAO(self.connector)
        with open(tasks_csv_path) as input_csv:
            total_tasks = sum(1 for _ in DictReader(input_csv))

        with open(tasks_csv_path) as input_csv, open(
            images_csv_path, "w"
        ) as output_csv:

            writer = DictWriter(
                output_csv,
                fieldnames=[
                    "project_id",
                    "task_id",
                    "annotation_id",
                    "view",
                    "label",
                    "annotated_pixels",
                    "image_path",
                ],
            )
            reader = DictReader(input_csv)
            writer.writeheader()
            for row in tqdm(
                reader, desc=f"Exporting tasks from {csv_name}", total=total_tasks
            ):
                project_id = row["ls_project_id"]
                task_id = row["ls_task_id"]
                patient_id = row["anonPatientId"]
                study_id = row["anonExaminationStudyId"]
                study_folder = os.path.join(root_path, patient_id, study_id)
                image_rows = task_dao.get_task_annotations(
                    project_id=project_id, task_id=task_id, study_path=study_folder
                )
                writer.writerows(image_rows)
