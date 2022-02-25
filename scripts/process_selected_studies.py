
import json
import os
from typing import List
from coma_db.mongo_dao import Connector, ImageMetadataDao
from tqdm import tqdm
from mammoannotator.mip_processor import DicomSeries
from matplotlib import pyplot as plt
from sort_studies import get_images
from datetime import datetime
from coma_db.utils import parse_DA_TM_as_datetime
base_path = "processed_images"

with open("/media/padmin/028F-4CCB/mri annotations/batch_1_studies.json") as file:
    batch_1_studies = json.load(file)

lookup_pipeline = [
    {
        # After importing the ris_mri_csv into mongo, 
        # the rows are matched by (Examination)AccessionNumber
        # to the study and the reporttexttext is added.
        '$lookup': {
            'from': 'ris_mri_csv', 
            'localField': 'dicom_tags.AccessionNumber.Value.0', 
            'foreignField': 'ExaminationAccessionNumber', 
            'as': 'ris_rows', 
            'pipeline': [
                {
                    '$project': {
                        'ReportTextText': 1, 
                        'cancer_code_left': 1, 
                        'cancer_code_right': 1
                    }
                }
            ]
        }
    }
]

connector_kwargs = dict(
        host="127.0.0.1",
        port=27017,
        username=None,
        password=None,
        db_name="coma_mri_preingest"
    )

connector = Connector(**connector_kwargs)
im_dao = ImageMetadataDao(connector)

series_collection = connector.db["preingest_series_3"]

intermediate_collection = connector.db['selected_studies']
final_collection = connector.db['selected_studies_with_row']

def get_tag(d:dict, tag:str, default_value=None):
    return d['dicom_tags'].get(tag, {"Value":default_value})["Value"]

def sub_in_study(series:List[dict]):
    for s in series:
        if sub_series(s):
            return True
    return False

def sub_series(s:dict):
    if "sub" in get_tag(s, "SeriesDescription", "")[0]:
        return True
    for im_type in get_tag(s, "ImageType", []):
            if "sub" in im_type.lower():
                return True
    return False

# def get_instances(s):
#     return [im_dao.get_by_id(i, obj=False) for i in s['instance_ids']]


def get_tags(d: dict, *tags: List[str]):
    """Get a dictionary of the requested tags"""
    return {t: get_tag(d, t) for t in tags}

def get_smallest(instances:List[dict], tag:str):
    """get the smallest value from all instances with the tag"""
    instances = sorted(instances, key=lambda x: get_tag(x, tag, '0'))
    return get_tag(instances[0], tag, '0')

def process_sub(mri_series, study_path, patient_id, study_id, selected_series):
    # plt.imshow(mri_series.windowed_mip("right", "axial"))
    # plt.show()
    # print(study_path)
    os.makedirs(study_path, exist_ok=True)
    get_images(mri_series, study_path)
    with open(os.path.join(study_path, "info.json"), "w") as file:
        json.dump({
            "patient_id":patient_id,
            "study_id": study_id,
            "selected_series": selected_series
        }, file, indent=4)


def parse_TM(tm) -> datetime:
    if "." in tm:
        return datetime.strptime(tm, "%H%M%S.%f")
    else:
        return datetime.strptime(tm, "%H%M%S")


def find_correct_series(sorted_series):
    """returns the first two series that have between one and two minute diff"""
    dt_old = parse_TM("000000")
    for i, s in enumerate(sorted_series):
        if sub_series(s):
            continue
        da = get_tag(s, "SeriesDate")[0]
        tm = get_tag(s, "SeriesTime")[0]
        dt = parse_DA_TM_as_datetime(da,tm)
        delta_minutes = (dt - dt_old).seconds/60
        # print(delta_minutes)
        if 1.0 < delta_minutes < 2.0:
            return sorted_series[i-1], sorted_series[i]
        dt_old = dt

def get_mri_series(s):
    connector = Connector(**connector_kwargs)
    instance_ids = s["instance_ids"]
    dao = ImageMetadataDao(connector)
    return DicomSeries.from_slice_ids(instance_ids, dao)

def process_delta_series(s1, s2):
    mri_s1 = get_mri_series(s1)
    mri_s2 = get_mri_series(s2)
    return mri_s2 - mri_s1

def process_study(study):
    try:
        connector = Connector(**connector_kwargs)
        im_dao = ImageMetadataDao(connector)

        series_collection = connector.db["preingest_series_3"]

        study_path = get_study_path(study)
        series = [series_collection.find_one(i) for i in study['series_ids']]
        sub = sub_in_study(series)
        sorted_series = sorted(series, key=lambda x: get_tag(x, "SeriesNumber"))
        if sub: # if there are subtraction images, then find the first subtraction and use it.
            for s in sorted_series:      
                if sub_series(s):
                    # print("Using series:", get_tag(s, "SeriesDescription"))
                    selected_series = (get_tag(s, 'SeriesDescription', 'UNK')[0], )
                    # print(get_tag(s, "ImageOrientationPatient"))
                    mri_series = get_mri_series(s)
                    process_sub(mri_series, study_path, study["patient_anon_ids"], study["study_uid"], selected_series)
                    break
        else:
            s1, s2 = find_correct_series(sorted_series)
            selected_series = get_tag(s2, 'SeriesDescription', 'UNK')[0], get_tag(s1, 'SeriesDescription', 'UNK')[0]
            # print(f"Using series:{get_tag(s1, 'SeriesDescription')} \n and {get_tag(s2, 'SeriesDescription')}")
            # print(get_tag(s1, "ImageOrientationPatient"))
            subtraction = process_delta_series(s1, s2)
            process_sub(subtraction, study_path, study["patient_anon_ids"], study["study_uid"], selected_series)
    except:
        print(f"Error with study {study['study_uid']}")
    
def get_study_path(study):
    study_safe_path = study["study_uid"].replace("/", "FSLASH")
    study_path = os.path.join("processed_images",study["patient_anon_ids"], study_safe_path)
    return study_path

def is_high_risk(report_text):
    for line in report_text.split('\n'):
            if "kod" in line.lower() and (("4" in line.lower()) or ("5" in line.lower()) or ("3" in line.lower())):
                return True
    return False

def study_generator():
    for study in intermediate_collection.aggregate(lookup_pipeline):
        study_path = get_study_path(study)
        report_rows = study["ris_rows"]
        if len(report_rows) > 0:
            report_text = report_rows[0].get("ReportTextText")
            if is_high_risk(report_text) and not study["study_uid"] in batch_1_studies:
        # if os.path.exists(study_path): #skip cases that hace been already processed
        #     continue
                yield study

def main_multiproc():
    from multiprocessing import Pool
    pool = Pool(15)
    for _ in tqdm(pool.imap_unordered(process_study, study_generator()), smoothing=0.005):
        pass
    
def count():
    for i in tqdm(study_generator()):
        pass
        
    # print("//////////////////////////////")
        # print(sub_series(s))
    #     # get series that have the same 
    #     for i, s in enumerate(sorted_series):
    #         print (get_tag(s, "ImageType", None))
    #         print(sub_series(s))
    #         if sub_series(s):
    #             process_sub(s["instance_ids"], s)
    #             break

main_multiproc()
# count()