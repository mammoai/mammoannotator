# This scrips was used on 2022-01-27 to create the first batch of images for the annotation task.
# Patients: 137it [11:43,  5.14s/it]
# studies: 187it [11:44,  3.77s/it]]
import pymongo
import os
from mammoannotator.mip_processor import DicomSeries
from mammoannotator.mri import list_dirs, ensure_folder_exists
from typing import List
from tqdm import tqdm
import numpy as np
from PIL import Image
from multiprocessing import Pool
import traceback

output_folder="/Users/annotator/Desktop/processed_images/"

mongo_host = "localhost"
mongo_port = 27017
client = pymongo.MongoClient(mongo_host, mongo_port)
db = client.dev_mri
collection = db['patients']
counter = 0

studies_pbar = tqdm(desc="studies")

def _get_sort_key(series: DicomSeries):
    return series.tags['series_number']


def select_series(paths: List[str]):
    series = []
    for path in paths:
        dicom_series = DicomSeries.from_path(path)
        series.append(dicom_series)
    series = sorted(series, key=_get_sort_key)
    content_times = [s.tags['acquisition_time'] for s in series]
    #print(content_times)
    return series[0], series[1]

def correct_study(study):
    good_folders = correct_study_folders(study)
    if len(good_folders) < 2:
        return False
    else:
        return True

def is_high_risk(patient):
    for study in patient['studies']:
        report_text = study.get('report_text', '')
        for line in report_text.split('\n'):
            if "kod" in line.lower() and (("4" in line.lower()) or ("5" in line.lower()) or ("3" in line.lower())):
                return True
    return False

def correct_study_folders(study):
    study_path = os.path.dirname(os.path.dirname(study['path']))
    folders = list_dirs(study_path)
    good_folders = []
    for f in folders:
        last_folder = os.path.split(f)[-1]
        if "t1_fl3d_tra_dynaViews" in last_folder and not "sub" in last_folder.lower():
            good_folders.append(f)
    return good_folders

def get_images(series: DicomSeries, study_path: str):
    r_sag = series.windowed_mip("right", "sagittal")
    Image.fromarray(r_sag).save(os.path.join(study_path, "sub_r_Sag.jpeg"))
    l_sag = series.windowed_mip("left", "sagittal")
    Image.fromarray(l_sag).save(os.path.join(study_path, "sub_l_Sag.jpeg"))
    r_ax = series.windowed_mip("right", "axial")
    r_ax = np.rot90(r_ax, 3)
    Image.fromarray(r_ax).save(os.path.join(study_path, "sub_r_Ax.jpeg"))
    l_ax = series.windowed_mip("left", "axial")
    l_ax = np.rot90(l_ax, 3)
    Image.fromarray(l_ax).save(os.path.join(study_path, "sub_l_Ax.jpeg"))
    return r_sag, l_sag, r_ax, l_ax 

def process_study(study: dict, patient_path: str):
    """{_id, patient_id, report_text, paths, study_date}"""
    try:
        study_path = os.path.join(patient_path, study['study_id'])
        ensure_folder_exists(study_path)
        good_folders = correct_study_folders(study)
        no_contrast, with_contrast = select_series(good_folders)
        subtracted = with_contrast - no_contrast
        get_images(subtracted, study_path)
        return 1
    except:
        print(f"Error processing study {patient_path}/{study['study_id']}")
        print(traceback.print_exc())
        return 0
    

def process_patient(patient: dict):
    """{
        "_id": "356e7a75575965496161324f676f3166316c334651513d3d",
        "studies": [{
            "study_id": "yFUIc1QIEISR3x5aeIX2iJHb4uVv43gXJPzUa8isgwKAX91RZQSX21YxMcTxJQiNYzBOCC06V1itxbGS+00oBA==",
            "report_text": "MRT THORAX UTAN IVK TVÅ  ÅR POST OP:\nStudie Qmed 31 GC1201. \n\nSedan föregående undersökning vid ett år post op 140319 har Makrolane injicerat djupt subkutant framför sternum ytterligare sammansmält till i stort sätt en större ”bubbla” belägen framför inferiora delen av sternum. Botten på ”gropen” är fortfarande något konvex framåt. Gropens djup minskat från 25 mm till 19 mm på inandad bild medan den ökat från 20 till 24 mm på utandad bild. Diskrepansen kan bero på olika maximal inandning och utandning mellan de två undersökningarna. Sannolikt ingen signifikant skillnad på ”gropens” djup. \n\n\nSkannad remiss, papperssvar\n \nTengvar, Magnus\n15:55   2015-04-27   Signering 2 Slutgiltigt svar: Tengvar, Magnus \n\n",
            "study_date": {
                "$date": "2015-03-28T00:00:00.000Z"
            }
        }],
        "n_studies": 1,
        "earliest_study_date": {
            "$date": "2015-03-28T00:00:00.000Z"
        }
    }"""
    patient_path = os.path.join(output_folder, patient['_id'])
    ensure_folder_exists(patient_path)
    counter = 0
    for study in patient['studies']:
        if not correct_study(study):
            continue
        counter += process_study(study, patient_path)
    return counter

def task_dispenser():
    for patient in collection.find():
        if not is_high_risk(patient):
            continue
        yield patient

def main_multiproc(n_proc):
    pool = Pool(processes=n_proc)
    tasks = task_dispenser()
    for n_studies in tqdm(pool.imap_unordered(process_patient, tasks), desc="Patients"):
        studies_pbar.update(n_studies)

def main():
    for patient in collection.find():
        if not is_high_risk(patient):
            continue
        n_studies = process_patient(patient)
        studies_pbar.update(n_studies)



if __name__ == "__main__":
    main_multiproc(n_proc=6)

