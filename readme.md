# Mammoannotator
Tools for setting up a Breast Cancer labeling app.

## Requirements

1. Docker. Follow the installation steps here: https://docs.docker.com/engine/install/
1. The images that will be annotated in the following folder structure:
```
- <root_folder>/
-- actual_csv.csv
-- <patient_id>/
--- <study_id>/
---- <x>_<x>_<x>_<x>_<x>_<x>_<x>_<laterality>_<view>.jpeg
```
Where `<x>` is whatever identifier you want to set; `<laterality>` is one of `l` or `r`; and `<view>` is one of `Ax` or `Sag`. All the images in a study are expected to have the same pixel dimensions. Missing combinations of laterality and view are replaced with black in the task image.

`actual_csv.csv` has a header row and contains at least 3 columns `anonpatientid, anonexaminationstudyid, reporttexttext` in any order. It is expected that the combination of patient_id and study_id are unique. The task creation script will look for those values according to the folders that it is visiting.

## Setting up the labeling app
You will need to run two containers in the following order:
### 1. LabelStudio
Navigate to a desired location. LS will create a `label_studio/` folder that will make the app require to be run from the same parent folder every time.

In the terminal run:

```
docker run -it -p 127.0.0.1:8080:8080 -v `pwd`/labelstudio:/label-studio/data heartexlabs/label-studio:latest
```
In the browser go to `http://localhost:8080` and create an account in the app. This account is only stored locally. The password can't be recovered but creating another account will allow you to access the same projects.

Once you have created a user and logged in, go to your account in the upper-right corner > "Account & Settings". There you will find a Token that is needed to set up the app from the API which Mammoannotator uses.

### 2. Mammoannotor:
First get the absolute path to your `<root_folder>` if you are using macOS, an absolute path looks like this: `/home/<user>/<path to your root_folder>/` let's call it `<abs_root_folder>`.

Now, in a new tab of your terminal, run:
```
docker run -v <abs_root_folder>:/opt/server_root -it --network host fcossio/mammoannotator:0.0
```
This is a secondary service that will do 2 things:
First, it will create a local http server for the images so that LS can read them. For security, it is only binding the interface `127.0.0.1:8000` so you will not be able to access it from outside your computer.

Second, it will start a bash terminal inside the container that has the environment ready to run the custom python tools.

Export your token to the terminal
```
export LS_TOKEN=<your token here>
```

Now run
```
mammoannotator project -t '<desired title of your LS project>'
```
If everything worked fine, you should be able to reload the "Projects" page in the app and see a new project there.

Now it is time to create the tasks for the project.

```
mammoannotator tasks
```
This script will go through each patient in the root folder creating a new task per each study. It will create a `crops/` folder inside the study where the new images are stored. And a csv with the ids and the cropping info in the `<root_folder>`

There are other parameters for the CLI, you can find them by running `mammoannotator --help`, `mammoannotator project --help` or `mammoannotator tasks --help`

If you enter to the project's page and reload, you should be able to see all the tasks. Happy labeling!


