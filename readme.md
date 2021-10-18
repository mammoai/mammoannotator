# Mammoannotator
Tools for setting up a Breast Cancer labeling app.

## Requirements

1. Docker. Follow the installation steps here: https://docs.docker.com/engine/install/
1. Python >= 3.8. Using an env manager such as **conda** is recommended. https://docs.conda.io/en/latest/miniconda.html
1. Git. https://git-scm.com/downloads
1. The images that will be annotated in the following folder structure:
```
<root_folder>/
    <csv_file>.csv
        <patient_id>/
            <study_id>/
                <x>_<x>_<x>_<x>_<x>_<x>_<x>_<laterality>_<view>.jpeg
```
Where `<x>` is whatever identifier you want to set; `<laterality>` is one of `l` or `r`; and `<view>` is one of `Ax` or `Sag`. All the images in a study are expected to have the same pixel dimensions. Missing combinations of laterality and view are replaced with black in the task image.

`<csv_file>.csv` has a header row and contains at least 3 columns `anonpatientid, anonexaminationstudyid, reporttexttext` in any order. It is expected that the combination of patient_id(anonpatientid) and study_id(anonexaminationstudyid) are unique and that the folder `<root_path>/<anonpatientid>/<anonexaminationstudyid>` exists.

## Setting up the labeling app

Two steps are needed:

### 1. LabelStudio

Navigate to a desired location. LS will create a `label_studio/` folder that will make the app require to be run from the same parent folder every time. This folder contains the database that the service uses, back this folder up regularly to avoid any data losses.

In the terminal run:

```
docker run -it -p 127.0.0.1:8080:8080 -v `pwd`/labelstudio:/label-studio/data heartexlabs/label-studio:latest
```
In the browser go to `http://localhost:8080` and create an account in the app. This account is only stored locally. The password can't be recovered but creating another account will allow you to access the same projects.

Once you have created a user and logged in, go to your account in the upper-right corner > "Account & Settings". There you will find a Token that is needed to set up the app from the API which Mammoannotator CLI uses.

### 2. Img server and Mammoannotor CLI

First create an isolated conda environment
```
conda create -n mammo python=3.8 -y && conda activate mammo
```

Get the absolute path to your `<root_folder>` (if you are using macOS, an absolute path looks like this: `/home/<user>/<path to your root_folder>/`) let's call it `<abs_root_folder>`.

Start a local http server for the images so that LS can read them. For security, it is only binding the interface `127.0.0.1:8000` so you will not be able to access it from outside your computer:
```
python -m http.server 8000 --bind 127.0.0.1 --directory <abs_root_folder>
```

In a new tab, install the mammoannotator cli:
```
conda activate mammo
pip install git+https://github.com/fcossio/mammoannotator
```

Export your token to the terminal
```
export LS_TOKEN=<your token here>
```

To validate that the CLI is working correctly, you may run
```
mammoannotator check
```

To create a new project from a csv, run
```
mammoannotator project --csv-path <path to your csv>
```
If everything worked fine, you should be able to reload the "Projects" page in the app and see a new project there with one task per row of the csv. Additionally you will get a copy of your csv with some extra columns named `<project_id>-MRI-<date>.csv` this will link the row with the ls_project and ls_task_id. It will be important for processing the annotations in the future.

There are other configurable parameters for the CLI, you can find them by running `mammoannotator --help`, `mammoannotator project --help`

Happy labeling!


