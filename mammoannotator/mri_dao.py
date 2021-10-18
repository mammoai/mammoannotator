from csv import DictReader, DictWriter
from tqdm.auto import tqdm
from datetime import datetime
import json
import os
from mammoannotator.mri import MRITask
from mammoannotator.labelstudio_api import LabelStudioAPI


class TaskDAO:
    def __init__(self, connector: LabelStudioAPI):
        self.connector = connector

    def create_task(self, task:MRITask, project_id, img_server_url, img_server_root):
        task.make_url(img_server_root, img_server_url)
        task_dict = json.dumps(task.as_dict())
        answer = self.connector.create_task(data=task_dict, project=project_id)
        task_id = answer['id']
        return task_id

class ProjectDAO:
    def __init__(self, connector:LabelStudioAPI):
        self.connector = connector
    
    def create_project(self, title:str,
        description:str, interface_config_path:str, instruction_path:str):

        # read the labeling interface config
        with open(interface_config_path) as file:
            config = "".join([l for l in file])
        # read the labeling interface config
        with open(instruction_path) as file:
            instructions = "".join([l for l in file])

        project = self.connector.create_project(
            title=title, description=description, 
            label_config=config, expert_instruction=instructions,
            created_by={"first_name":"Admin", "last_name":"", "email":""},
            show_instruction=True, show_skip_button=True,
            enable_empty_annotation=False)
        return project['id']
    
    def create_mri_project_from_csv(self, csv_path,
        interface_config_path:str, instruction_path:str,
        root_path:str, img_server_url:str):
        """Create a Label Studio project and create tasks based on a CSV file.

        Args:
            csv_path (str): A csv that contains at least the following columns:
             'anonpatientid', 'anonexaminationstudyid', 'reporttexttext'.
            interface_config_path (str): Path to XML formatted config.
            instruction_path (str): Path to HTML formatted instructions.
            root_path (str): Path where the patients' folders exist. This is
             also the root of the img server
            img_server_url (str): base url where the images will be found 
        """
        csv_parent, csv_basename = os.path.split(csv_path)
        today = datetime.now().strftime("%Y-%m-%d")
        title = f"MRI {today}"
        description = f"Based on {csv_basename}"
        task_dicts = []
        # preventive read first
        with open(csv_path, newline='') as file:
            reader = DictReader(file)
            fields = reader.fieldnames
            assert 'anonpatientid' in fields
            assert 'anonexaminationstudyid' in fields
            assert 'reporttexttext' in fields
            for row in reader:
                assert os.path.exists(
                    os.path.join(
                        root_path,
                        row['anonpatientid'],
                        row['anonexaminationstudyid']))
                task_dicts.append(row)
        # create project
        print(f"Creating {title} {description}")
        project_id = self.create_project(title, description,
            interface_config_path, instruction_path)
        print(f"Successfullly created project {project_id}")
        # now send all tasks to labelstudio
        task_dao = TaskDAO(self.connector)
        new_csv_path = os.path.join(csv_parent, f"{project_id}-MRI-{today}.csv")
        out_fieldnames = fields + ["ls_project_id", 'ls_task_id',
            'left_sagittal', 'right_sagittal', 'left_axial', 'right_axial']
        with open(new_csv_path, "w") as file:
            writer = DictWriter(file, out_fieldnames)
            writer.writeheader()
            for task_dict in tqdm(task_dicts, desc="Creating tasks"):
                task = MRITask.from_csv_row(root_path, task_dict)
                task_id = task_dao.create_task(task, project_id, img_server_url,
                    root_path)
                # Add information to output dict
                task_dict['ls_project_id'] = project_id
                task_dict['ls_task_id'] = task_id
                task_dict["left_sagittal"] = task.crop_details.get(
                    'left_sagittal', None)
                task_dict["right_sagittal"] = task.crop_details.get(
                    'right_sagittal', None)
                task_dict["left_axial"] = task.crop_details.get(
                    'left_axial', None)
                task_dict["right_axial"] = task.crop_details.get(
                    'right_axial', None)
                writer.writerow(task_dict)
    