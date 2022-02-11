import pymongo

mongo_host = "localhost"
mongo_port = 27017
client = pymongo.MongoClient(mongo_host, mongo_port)
db = client.real_mri
collection = db.mrbrost

query = [
    {
        '$group': {
            '_id': '$SeriesInstanceUID', 
            'PatientID': {'$first': '$PatientID'}, 
            'StudyInstanceUID': {'$first': '$StudyInstanceUID'}, 
            'StudyDate': {'$first': '$StudyDate'}, 
            'n_files': {'$count': {}}, 
            'path': {'$push': '$path'}
        }
    }, 
    {
        '$group': {
            '_id': '$StudyInstanceUID', 
            'patient_id': {'$first': '$PatientID'},
            'study_date': {'$first': '$StudyDate'}, 
            'n_series': {'$count': {}}, 
            'path': {'$first': {'$first': '$path'}}
        }
    },
    # {
    #     '$group': {
    #         '_id': '$patient_id', 
    #         'studies': {'$push': '$_id'}, 
    #         'n_studies': {'$count': {}},
    #         'paths': {'$push': '$path'}
    #     }
    # },
    {
        '$count': 'total'
    }
]

q = collection.aggregate(query, allowDiskUse=True)
print(next(q))

