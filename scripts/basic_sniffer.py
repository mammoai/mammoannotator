from shutil import ExecError
import pymongo
import pydicom
import os
from mammoannotator.mri import list_files, list_dirs
from tqdm import tqdm
from datetime import datetime

root_path = "/Volumes/MRBROST"

mongo_host = "localhost"
mongo_port = 27017
client = pymongo.MongoClient(mongo_host, mongo_port)
db = client.anon_mri_2
collection = db.mrbrost

def parse_age_string(age_string):
    """return the number of years as a float considering 1Y=12M=52W=365D"""
    if age_string == "":
        return None
    elif "Y" in age_string:
        return float(age_string.split("Y")[0])
    elif "M" in age_string:
        return int(age_string.split("M")[0])/12
    elif "W" in age_string:
        return int(age_string.split("W")[0])/52
    elif "D" in age_string:
        return int(age_string.split("D")[0])/365
    else:
        return None

def parse_time(time_string):
    """return a datetime object from a string"""
    time_string = time_string[0]
    if time_string == "":
        return None
    if "." in time_string:
        return datetime.strptime(time_string, "%H%M%S.%f")
    else:
        return datetime.strptime(time_string, "%H%M%S")

parsers = {
    "DA": lambda x: datetime.strptime(x[0], '%Y%m%d'), # date
    # "TM": lambda x: parse_time, # time
    "PN": lambda x: " ".join([v for v in x[0].values()]), # person name
    "CS": lambda x: ", ".join([v for v in x]), # character set
    "LO": lambda x: ", ".join([v for v in x]), # long string
    "LT": lambda x: ", ".join([v for v in x]), # long string
    "SH": lambda x: ", ".join([v for v in x]), # short string
    "IS": lambda x: int(x[0]), # integer string
    "UI": lambda x: x[0], # unique identifier
    "AS": parse_age_string, # age string
    "DS": lambda x: float(x[0]), # decimal string
}

def get_value(ds_dict_elem):
    """return the value of a dicom tag"""
    try:
        if ds_dict_elem["vr"] == "SQ":
            return [{pydicom.datadict.keyword_for_tag(k):get_value(v) for k,v in elem.items()} for elem in ds_dict_elem['Value']]
        elif ds_dict_elem["vr"] in parsers.keys():
            return parsers[ds_dict_elem["vr"]](ds_dict_elem["Value"])
        else:
            return ds_dict_elem["Value"]
    except:
        return "Could not parse"

def create_dict(ds:pydicom.dataset.Dataset):
    """return a dict with the dicom tags as keys and the values as values"""
    try:
        ds_dict = ds.to_json_dict()
    except:
        return {"error": "Could not parse", "path": ds.filename}
    replaced = {pydicom.datadict.keyword_for_tag(k): get_value(v) for k, v in ds_dict.items()}

    return replaced
    



def main(root_path):
    pbar_patient = tqdm(desc="patients")
    pbar_study = tqdm(desc="studies")
    pbar_series = tqdm(desc="series")
    pbar_file = tqdm(desc="files")
    pbar_skips = tqdm(desc="skips")
    for patient_folder in list_dirs(root_path):
        pbar_patient.update()
        for study_folder in list_dirs(patient_folder):
            pbar_study.update()
            for series_folder in list_dirs(study_folder):
                pbar_series.update()
                dcm_files = list_files(series_folder, ".dcm")
                if len(dcm_files) == 0:
                    pbar_skips.update()
                    break
                ds = pydicom.dcmread(dcm_files[0])
                # if ds.PatientID != os.path.split(patient_folder)[1]:
                #     pbar_skips.update()
                #     break
                # if ds.StudyInstanceUID != os.path.split(study_folder)[1]:
                #     pbar_skips.update()
                #     break
                for dcm_file in dcm_files:
                    dcm_dict = pydicom.dcmread(dcm_file)
                    replaced = create_dict(dcm_dict)
                    # {
                    #     ele.keyword: ele.value.formatted()
                    #     for ele in 
                    #     if ele.keyword not in ['PixelData']
                    # }
                    replaced['path'] = dcm_file
                    collection.insert_one(replaced)
                    pbar_file.update()
                    break #use only one doc per 
            
            

if __name__ == '__main__':
    for folder in list_dirs(root_path):
        print(f"Analysing {folder}")
        main(folder)