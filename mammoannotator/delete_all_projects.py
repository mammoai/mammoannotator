import requests
from mammoannotator.labelstudio_api import LabelStudioAPI
import os


token = os.environ.get("LS_TOKEN", None)
assert token is not None, "export LS_TOKEN as env variable and try again"
api = LabelStudioAPI(url="http://localhost:8080", token=token)
projects = api.list_projects()
for project in projects:
    print(project['results'])
    # api.delete_project(int(project['id']))
    # print(f"DELETED {id}: {project['title']}")
