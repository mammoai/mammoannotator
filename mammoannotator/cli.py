from argparse import ArgumentParser
import sys
import os
from mammoannotator.mri_dao import ProjectDAO
from mammoannotator.labelstudio_api import LabelStudioAPI

def create_project(raw_args):
    """The csv must be in the root_path where all the patients' folders are."""
    dirname = os.path.dirname(__file__)
    default_config_path = os.path.join(dirname, "config.xml")
    default_instruction_path = os.path.join(dirname, "instruction.html")
    parser = ArgumentParser()
    parser.add_argument("--csv-path", type=str, required=True)
    parser.add_argument("--interface-config", "-c", type=str, 
        default=default_config_path)
    parser.add_argument("--expert-instruction", "-i", type=str, 
        default=default_instruction_path)
    parser.add_argument('--ls-url', default="http://localhost:8080")
    parser.add_argument("--img-server-url", default="http://localhost:8000")
    args = parser.parse_args(raw_args)
    token = os.environ.get("LS_TOKEN", None)
    assert token is not None, "export LS_TOKEN as env variable and try again"
    root_path, _ = os.path.split(args.csv_path)
    connector = LabelStudioAPI(args.ls_url, token)
    project_dao = ProjectDAO(connector)
    project_dao.create_mri_project_from_csv(
        args.csv_path, args.interface_config, 
        args.expert_instruction, root_path, 
        args.img_server_url)

def check_connection(raw_args):
    parser = ArgumentParser()
    parser.add_argument('--ls-url', default="http://localhost:8080")
    args = parser.parse_args(raw_args)
    token = os.environ.get("LS_TOKEN", None)
    assert token is not None, "export LS_TOKEN as env variable and try again"
    connector = LabelStudioAPI(args.ls_url, token)
    connector.is_valid()
    print(f"Successful connection with LabelStudio at {args.ls_url}")
    
def main(raw_args=sys.argv[1:]):
    parser = ArgumentParser()
    parser.add_argument("action", choices=["project", "check"])
    args, other_args = parser.parse_known_args(raw_args)
    if args.action == "project":
        create_project(raw_args[1:])
    elif args.action == 'check':
        check_connection(raw_args[1:])

if __name__ == "__main__":
    main(sys.argv[1:])