from argparse import ArgumentParser
import json
import requests
import sys
import os
from csv import DictWriter
from mammoannotator.mri import MRITask
import pandas as pd

def create_project(raw_args):
    print(__file__)
    default_config_path = os.path.join(os.path.dirname(__file__), "config.xml")
    parser = ArgumentParser()
    parser.add_argument("--title", "-t", type=str, required=True)
    parser.add_argument("--interface-config", "-c", type=str, default=default_config_path)
    args = parser.parse_args(raw_args)
    token = os.environ.get("LS_TOKEN", None)
    assert token is not None, "export LS_TOKEN as env variable and try again"
    # read the labeling interface config
    with open(args.interface_config) as file:
        config = "".join([l for l in file])
    headers={
        "ContentType": "application/json",
        "Authorization": f"Token {token}"
    }
    url="http://localhost:8080/api/projects/"
    data={
        "title": args.title,
        "description": "this is a test",
        "label_config": config,
        "expert_instruction": "This is a test",
        "show_instruction": True,
        "show_skip_button": True,
        "enable_empty_annotation": False,
        "show_annotation_history": True,
        "maximum_annotations": 1,
        "is_published": True,
        "is_draft": False,
        "created_by": 
        {
            "first_name": "admin",
            "last_name": "",
            "email": "",
            "avatar": "AD"

        },
        "show_collab_predictions": False,
        "sampling": "Sequential sampling",
        "show_ground_truth_first": True,
        "show_overlap_first": True,
        "overlap_cohort_percentage": 0,
        "parsed_label_config": config,
        "evaluate_predictions_automatically": False,
    }
    # response = requests.get(url,headers=headers)
    response = requests.post(url, data=data, headers=headers)
    print(response.json())

def create_tasks(raw_args):
    parser = ArgumentParser()
    parser.add_argument("--level", choices=["study", "patient", "root"], default="root")
    parser.add_argument("--folder", type=str, default="/opt/server_root")
    parser.add_argument("--project-id", type=int, default=0)
    parser.add_argument('--img-server-root', default="/opt/server_root/")
    parser.add_argument("--img-server-url", default="http://localhost:8000")
    parser.add_argument('--ls-url', default="http://localhost:8080/api/tasks/")
    parser.add_argument('--assessment-csv-fn', default="csv_actual.csv")
    args = parser.parse_args(raw_args)
    token = os.environ.get("LS_TOKEN", None)
    assert token is not None, "export LS_TOKEN as env variable and try again"
    
    headers={
        "ContentType": "application/json",
        "Authorization": f"Token {token}"
    }

    if args.level == "study":
        tasks = [MRITask.from_study_folder(args.folder)]
    if args.level == "patient":
        tasks = MRITask.from_patient_folder(args.folder)
    if args.level == "root":
        tasks = MRITask.from_root_folder(args.folder)
    csv_path = os.path.join(args.folder, f"project{args.project_id}_tasks.csv")
    assert not os.path.exists(csv_path), f"This is a safeguard to avoid overwriting. There is already a csv at {csv_path}. If you really want to run it, you can move or delete the file and run again."
    
    assessment_csv_path = os.path.join(args.img_server_root, args.assessment_csv_fn)
    assessment_df = pd.read_csv(assessment_csv_path)

    with open(csv_path, "w") as file:
        writer = DictWriter(file, fieldnames=["task_id", "patient_id", "study_id", "left_sagittal", "right_sagittal", "left_axial", "right_axial"])
        writer.writeheader()
        for task in tasks:
            task.make_url(args.img_server_root, args.img_server_url)
            task.set_assessment_from_csv(assessment_df)
            task_dict = json.dumps(task.as_dict())
            data = {
                "data": task_dict,
                "is_labeled": False,
                "overlap": 0,
                "project": args.project_id,
                "annotations": []
            }
            response = requests.post(url=args.ls_url, headers=headers, data=data)
            assert response.status_code == 201, f"task creation failed: {response.json()}"
            task_id = response.json()['id']
            writer.writerow({
                "task_id":task_id, 
                "patient_id":task.patient_id,
                "study_id": task.study_id,
                "left_sagittal": task.crop_details.get('left_sagittal', None),
                "right_sagittal": task.crop_details.get('right_sagittal', None),
                "left_axial": task.crop_details.get('left_axial', None),
                "right_axial": task.crop_details.get('right_axial', None),
                })

def main(raw_args=sys.argv[1:]):
    parser = ArgumentParser()
    parser.add_argument("action", choices=["project", "tasks"])
    args, other_args = parser.parse_known_args(raw_args)
    if args.action == "project":
        create_project(raw_args[1:])
    elif args.action == "tasks":
        create_tasks(raw_args[1:])

if __name__ == "__main__":
    main(sys.argv[1:])