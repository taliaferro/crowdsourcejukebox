
# A very simple Flask Hello World app for you to get started with...

from flask import Flask, jsonify
import pymongo
from flask_pymongo import PyMongo
from bson.json_util import dumps

app = Flask(__name__)
flaskpymongo=PyMongo(app, uri="mongodb://csjb_client:hU3LkvSY4CfMeNyV@crowdsourcejukebox-shard-00-00-shfa2.mongodb.net:27017,crowdsourcejukebox-shard-00-01-shfa2.mongodb.net:27017,crowdsourcejukebox-shard-00-02-shfa2.mongodb.net:27017/test?ssl=true&replicaSet=CrowdsourceJukebox-shard-0&authSource=admin&retryWrites=true&w=majority")
mclient = flaskpymongo.cx

@app.route('/')
def hello_world():
    # return 'Hello from Flask!'
    return jsonify(list(mclient["meta"]["sessions"].find({},{"_id": 0})))
