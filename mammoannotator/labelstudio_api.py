from dataclasses import dataclass
import requests


@dataclass
class LabelStudioAPI:
    """Should mostly match Label Studio API (v2) https://labelstud.io/api"""

    url: str
    token: str

    # Utils

    def headers(self):
        return {
            "ContentType": "application/json",
            "Authorization": f"Token {self.token}"
        }

    def is_valid(self, raise_exception=True):
        """Check that the connection is working"""
        response = self._get_projects()
        if raise_exception:
            self._check_status_code(response, 200)
        return response.status_code == 200

    @staticmethod
    def _check_status_code(response, expected_code: int):
        assert response.status_code == expected_code, f"Failed request: {response.json()}"

    # Projects

    def _get_projects(self):
        url = f'{self.ls_url}/api/projects'
        return requests.get(url=url, headers=self.headers())

    def list_projects(self):
        """Return a list of the projects that you've created"""
        response = self._get_projects_request()
        self._check_status_code(response, 200)
        return response.json()

    def _get_project_by_title(self, title: str) -> dict:
        """Get the first project that matches the title"""
        for project in self.list_projects():
            if project["title"] == title:
                return project

    def get_project_id_by_title(self, title):
        """Get the id of the first project that matches the title"""
        return self._get_project_by_title(title)['id']

    def create_project(self,
                       title: str,
                       description: str,
                       label_config: str,
                       expert_instruction: str,
                       show_instruction: bool,
                       show_skip_button: bool,
                       created_by: dict,
                       enable_empty_annotation: bool = False,
                       show_annotation_history: bool = True,
                       organization: int = None,
                       color: str = None,
                       maximum_annotations: int = 1,
                       is_published: bool = True,
                       model_version: str = None,
                       is_draft: bool = False,
                       min_annotations_to_start_training: int = 1,
                       show_collab_predictions: bool = True,
                       sampling: str = None,
                       show_ground_truth_first: bool = True,
                       show_overlap_first: bool = True,
                       overlap_cohort_percentage: int = 0,
                       task_data_login: str = None,
                       task_data_pasword: str = None,
                       control_weights: dict = None,
                       evaluate_predictions_automatically: bool = True) -> dict:
        """
        Create a project and set up the labeling interface in Label Studio using
        the API.

        Args:
            title (str): Project name. Must be between 3 and 50 chars long.
            description (str): Project Description
            label_config (str): Label config in XML format. See more about it in
             documentation
            expert_instruction (str): Labeling instructions in HTML format.
            show_instruction (bool): Show instructions to the annotator before
             they start
            show_skip_button (bool): Show a skip button in interface and allow
             annotators to skip the task
            created_by (dict): {'first_name':str, 'last_name':str, 'email':str}
            enable_empty_annotation (bool, optional): Allow annotators to submit
             empty annotations. Defaults to False.
            show_annotation_history (bool, optional): Show annotation history to
             annotator. Defaults to True.
            organization (int, optional): Organization id. Defaults to None.
            color (str, optional): Less than 16 chars. Color for the project
             card. Defaults to None.
            maximum_annotations (int, optional): Maximum number of annotations
             for one task. If the number of annotations per task is equal or
             greater to this value, the task is completed (is_labeled=True).
             Defaults to 1.
            is_published (bool, optional): Whether or not the project is
             published to annotators. Defaults to True.
            model_version (str, optional): Machine Learning model version.
             Defaults to None.
            is_draft (bool, optional): Whether or not the project is in the
             middle of being created. Defaults to False.
            min_annotations_to_start_training (int, optional): Minimum number
             of completed tasks after which model training is started. Defaults to 1.
            show_collab_predictions (bool, optional): [description]. Defaults
             to True.
            sampling (str, optional): [description]. Defaults to None.
            show_ground_truth_first (bool, optional): [description]. Defaults
             to True.
            show_overlap_first (bool, optional): [description]. Defaults to
             True.
            overlap_cohort_percentage (int, optional): [description]. Defaults
             to 0.
            task_data_login (str, optional): [description]. Defaults to None.
            task_data_pasword (str, optional): [description]. Defaults to None.
            control_weights (dict, optional): [description]. Defaults to None.
            evaluate_predictions_automatically (bool, optional): [description].
             Defaults to True.

        Returns:
            dict: see https://labelstud.io/api#operation/api_projects_create
        """
        url = f'{self.url}/api/projects/'
        request_data = {
            "title": title,
            "description": description,
            "label_config": label_config,
            "expert_instruction": expert_instruction,
            "show_instruction": show_instruction,
            "show_skip_button": show_skip_button,
            "enable_empty_annotation": enable_empty_annotation,
            "show_annotation_history": show_annotation_history,
            "organization": organization,
            "color": color,
            "maximum_annotations": maximum_annotations,
            "is_published": is_published,
            "model_version": model_version,
            "is_draft": is_draft,
            "created_by": created_by,
            "min_annotations_to_start_training": min_annotations_to_start_training,
            "show_collab_predictions": show_collab_predictions,
            "sampling": sampling,
            "show_ground_truth_first": show_ground_truth_first,
            "show_overlap_first": show_overlap_first,
            "overlap_cohort_percentage": overlap_cohort_percentage,
            "task_data_login": task_data_login,
            "task_data_password": task_data_pasword,
            "control_weights": control_weights,
            "evaluate_predictions_automatically": evaluate_predictions_automatically
        }
        response = requests.post(url=url,
                                 headers=self.headers(),
                                 data=request_data)
        self._check_status_code(response, 201)
        return response.json()


    # Tasks

    def create_task(self,
                    data: str,
                    project: int,
                    meta: str = None,
                    is_labeled=False,
                    overlap=0,
                    file_upload: int = None,
                    annotations=lambda: list()):
        """Create a new labeling task in Label Studio

        Args:
            data (json formatted str): User imported or uploaded data for a
             task. Data is formatted according to the project label config. You
             can find examples of data for your project on the Import page in
             the Label Studio Data Manager UI.
            project (int): Project ID for this task
            meta (json formatted str, optional): Meta is user imported 
             (uploaded) data and can be useful as input for an ML Backend for
             embeddings, advanced vectors, and other info. It is passed to ML
             during training/predicting steps. Defaults to None.
            is_labeled (bool, optional): True if the number of annotations for
             this task is greater than or equal to the number of
             maximum_completions for the project. Defaults to False.
            overlap (int, optional): Number of distinct annotators that
             processed the current task. Defaults to 0.
            file_upload (int, optional): Uploaded file used as data source for
             this task. Defaults to None.
            annotations (Array of objects (Annotation), optional): Annotations
             for the task. Defaults to empty list.

        Returns:
            dict: for example:
             {
                "id": 0,
                "data": { },
                "meta": { },
                "created_at": "2019-08-24T14:15:22Z",
                "updated_at": "2019-08-24T14:15:22Z",
                "is_labeled": True,
                "overlap": 0,
                "project": 0,
                "file_upload": 0,
                "annotations": [{}]
             }
        """
        url = f"{self.url}/api/tasks/"
        request_data = dict(data=data,
                            meta=meta,
                            is_labeled=is_labeled,
                            overlap=overlap,
                            project=project,
                            file_upload=file_upload,
                            annotations=annotations)
        response = requests.post(url=url,
                                 headers=self.headers(),
                                 data=request_data)
        self._check_status_code(response, 201)
        return response.json()
