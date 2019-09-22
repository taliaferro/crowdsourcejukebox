import pymongo
import time
import os
import logging
from dotenv import load_dotenv

load_dotenv()

print("cleanup started", flush=True)
# print(str(list(os.environ)), flush=True)

INACTIVE_TIMEOUT =  5 # minutes
client = pymongo.MongoClient(os.environ["MONGO_URI"])

while(True):
    now = int(time.time())
    setlists = client["setlists"].list_collection_names()
    to_drop = client["meta"]["sessions"].find({"lastaccessed":{"$lt": now - (60*INACTIVE_TIMEOUT)}})
    to_drop = [s["publicID"] for s in to_drop]
    if to_drop != []:
        print(to_drop, flush=True)
        for s in to_drop:
            if s in setlists:
                client["setlists"][s].drop()
        client["meta"]["sessions"].delete_many({"lastaccessed":{"$lt": now - (60*INACTIVE_TIMEOUT)}})
    time.sleep(60 * INACTIVE_TIMEOUT)
