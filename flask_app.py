# app.py
import linecache
import time
import datetime
import random
import json
import uuid
import os
import sys
import urllib.parse

from flask import Flask, send_file, render_template, abort, jsonify, redirect, request, make_response
from itsdangerous import Signer
from werkzeug.exceptions import HTTPException

import pymongo
from flask_pymongo import PyMongo
from bson.json_util import dumps

import spotipy
import spotipy.util as util
from spotipy.oauth2 import SpotifyClientCredentials

# TODO: make "submit" route and API endpoint'''
#     search endpoint'''

# TODO: remember user votes for next visit'''
#    rework css so entire td is "up" or "down"'''
#    in view function, determine which songs the user has voted on'''
#    apply "up" and "down" classes when rendering template'''
#    correct displayed vote counts with JS'''

'''# TODO: add "settings" panel on player load'''#Settings panel styling made. Settings not implemented.
'''#    Don't play explicit songs'''
'''#    Require CAPTCHA/email to vote'''
'''#    '''
'''#    Songs need <X> votes to play'''

'''# TODO: Fallback Playlist'''
'''#    "set-fallback" API endpoint, takes Spotify URI and adds all songs with 0 upvotes'''
'''#    modal popup in player (to bypass autoplay blocker)'''
'''#    suggest Spotify featured playlists, search option'''
'''#    flexbox playlist image + name/author below, row flex with wrap'''

'''# TODO: "remove song" option in host control panel'''

'''# TODO: Scheduler task queue in mongodb'''

'''LAUNCH TODOS'''
# TODO: Pick a production WSGI server (Waitress, GUnicorn, CherryPy, etc)'''
# TODO: Migrate to either EC2 or a closet machine'''
# TODO: Figure out SSL (LetsEncrypt)'''

# GLOBALS:
site_location = "http://www.crowdsourcejukebox.com/"
inactive_timeout = 5 # minutes before an inactive client expires

#itsdangerous signer
secret_key = os.environ["SIGNER_KEY"]

# Globals for Spotify
client_id = 'e098696a1beb48fb9db404c76148a2f7'
client_secret =  os.environ["SP_CLIENT_SECRET"]
client_credentials_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)

# Spotify object
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
sp.trace = False;

#Helper Functions
def newID():
    existing_sessions = [x["publicID"] for x in session_db.find()]
    adj1 = linecache.getline('other/adjectives.txt', random.randint(1,247)).strip()
    # adj1 = adj1.strip() + "-"
    # adj2 = linecache.getline('other/adjectives.txt', random.randint(1,247)).strip()
    # adj2 = adj2.strip() + "-"
    noun = linecache.getline('other/nouns.txt', random.randint(1,857)).strip()
    noun = noun.strip()
    # ID = adj1 + adj2 + noun
    ID = adj1 + noun
    if ID in existing_sessions:
        ID = newID(existing_sessions = existing_sessions)

    now = int(time.time())
    killtime = datetime.datetime.now() + datetime.timedelta(minutes=inactive_timeout)

    toinsert = {}
    toinsert["display"] = adj1.capitalize() + noun.capitalize()
    toinsert["publicID"] = ID
    toinsert["privateID"] = str(uuid.uuid4())
    toinsert["_id"] = toinsert["privateID"]
    toinsert["generated"] = now
    toinsert["lastmodified"] = now
    toinsert["lastread"] = now
    toinsert["lastaccessed"] = now
    toinsert["guests"] = []
    # app.apscheduler.add_job(func=killSession, trigger='date', next_run_time=killtime, args=[toinsert['privateID']], id='close-'+toinsert["publicID"])
    session_db.insert_one(toinsert)
    toinsert.pop("_id")

    # setlist_db[ID].insert_many(list(setlist_db["master-example"].find({}, {"_id": 0})))

    return toinsert

def killSession(id, hard=False):
    todelete = session_db.find_one({"privateID": id})
    if todelete is None:
        return
    now = time.time()
    if(hard or todelete["lastaccessed"] < now - (inactive_timeout*60)):
        setlist_db[todelete["publicID"]].drop()
        session_db.delete_one({"privateID":id})
    else:
        killtime = datetime.datetime.now() + datetime.timedelta(minutes=inactive_timeout)
        #app.apscheduler.add_job(func=killSession, trigger='date', next_run_time=killtime, args=[id], id='close-'+todelete["publicID"]+random.randint(1000))

def killHard(id):
    killSession(id, hard=True)

#App Config
app = Flask(__name__)
# scheduler = APScheduler()
# scheduler.init_app(app)
# scheduler.start()

flaskpymongo=PyMongo(app, uri=os.environ["MONGO_URI"])
mclient = flaskpymongo.cx
setlist_db = mclient["setlists"]
session_db = mclient["meta"]["sessions"]
# session_db.insert_one({"key": "val"})
# with open("logs.txt", "a") as logfile:
#     # logfile.write("mclient.list_databases()")
#     logfile.write(str(list(mclient.list_databases())))

# @app.route("/favicon.ico")
# def favicon():
#     return redirect("http://www.crowdsourcejukebox.com/content/images/favicon.ico"), 301
#
# # Flask Pages Begin Here
#
@app.route("/")
def home():
    init_id = newID()
    # return jsonify(init_id)
    return render_template("index.html", init_id = json.dumps(init_id))

@app.route('/listen/')
def player():
    return render_template("player.html")

@app.route("/vote/")
def voteredir():
    return redirect("https://www.crowdsourcejukebox.com/")

@app.route("/vote/<string:publicID>/")
def vote(publicID):
    publicID = publicID.lower();
    now = int(time.time())
    if(publicID == "vote"):
        return redirect("https://www.crowdsourcejukebox.com/")
    session_info = session_db.find_one({"publicID": publicID},{"_id":0})
    if session_info is None:
        abort(404)
    session_db.update_one({"publicID": publicID}, {"$set":{"lastaccessed": now, "lastread":now}})
    current_playlist = list(setlist_db[publicID].find({"played": 0}, {"_id":0}).sort("upvotes", -1))

    # print(publicID + "-guest")
    # print(current_playlist)

    if current_playlist != []:
        tracks = sp.tracks([x["uri"] for x in current_playlist])["tracks"]
        for t in range(len(tracks)):
            curr_track = current_playlist[t]
            if publicID + "-guest" in request.cookies:
                if "upvoters" in curr_track.keys() and request.cookies[publicID + "-guest"] in curr_track["upvoters"]:
                    curr_track["vote"] = "up"
                    # curr_track["upvotes"] -= 1
                elif "downvoters" in curr_track.keys() and request.cookies[publicID + "-guest"] in curr_track["downvoters"]:
                    curr_track["vote"] = "down"
                    # curr_track["upvotes"] += 1
                else:
                    curr_track["vote"] = "neutral"
            else:
                curr_track["vote"] = "neutral"
            curr_track["image"] = tracks[t]["album"]["images"][1]["url"]
            curr_track["name"] = tracks[t]["name"]
            # curr_track["album"] = tracks[t]["album"]["name"]
            curr_track["artist"] = tracks[t]["artists"][0]["name"]
    resp =  make_response(render_template("vote.html", publicID=publicID, tracks = current_playlist))
    hancock = Signer(str(secret_key), salt=str(session_info['privateID']))
    if(publicID + "-guest") not in request.cookies:
        guestID = bytes(str(uuid.uuid4()), "utf-8")
        resp.set_cookie(publicID + "-guest",
                        value=hancock.sign(guestID),
                        expires=datetime.datetime.now() + datetime.timedelta(hours=1))
    else:
        if(not hancock.validate(request.cookies.get(publicID + "-guest"))):
            abort(401)
        # guestID = hancock.unsign(request.cookies.get(publicID + "-guest"))
    return resp

@app.route("/submit/<string:publicID>/")
def search(publicID):
    publicID = publicID.lower();
    now = int(time.time())
    session_info = session_db.find_one({"publicID": publicID},{"_id":0})
    if session_info is None:
        return redirect("http://www.crowdsourcejukebox.com/"), 301
    session_db.update_one({"publicID": publicID}, {"$set":{"lastaccessed": now, "lastread":now}})
    hancock = Signer(secret_key, salt=session_info['privateID'])
    if(publicID + "-guest") not in request.cookies:
        return redirect("http://csjb.cc/" + publicID)
    else:
        if(not hancock.validate(request.cookies.get(publicID + "-guest"))):
            abort(401)

    query = request.query_string.decode("UTF-8")
    if(query != ""):
        query = query[query.index('query='):]
        query = query[query.index('=')+1:]
        query = query if "&" not in query else query[:query.index("&")]
        query = urllib.parse.unquote_plus(query)
        results = sp.search(query, limit=20)["tracks"]["items"]
        tracks = [{"uri": result["uri"],
                   "image": result["album"]["images"][0]["url"],
                   "name": result["name"],
                   "artist": result["artists"][0]["name"]} for result in results]
        return render_template("results.html", tracks = tracks, publicID = publicID, prev_query = query)
    else:
        return render_template("search.html", publicID=publicID)

@app.route("/submit/")
def submitredir():
    return redirect("http://www.crowdsourcejukebox.com/"), 301

# UTILITY ROUTES

@app.route('/api/', methods=['POST'])
def api():
    now = int(time.time())
    form = {key:request.form[key] for key in request.form.keys()}
    authorized_requests = ["newID", "unload", "setlist", "updates", "public", "playnext", "vote", "submit"]
    if "req" not in form.keys() or form["req"] not in authorized_requests:
        abort(400)

    return_obj = {}
    if form["req"] == "newID":
        return_obj = newID()
        killSession(form["oldID"], hard = True)
    if form["req"] == "unload":
        killSession(form["oldID"], hard = True)
    if form["req"] == "playnext":
        publicID = session_db.find_one({"privateID": form["privateID"]})["publicID"]
        return_obj = list(setlist_db[publicID].find({"played": 0, "upvotes": {"$gte": 0}}))
        if(return_obj == []):
            past_played = [x for x in setlist_db[publicID].find({"played": 1},{"_id":0})]
            top_played = sorted(past_played, reverse=True, key = lambda i: i["upvotes"])
            if(len(top_played)>20):
                top_played = top_played[:len(top_played)/2]
            seeds = []
            for i in range(4):
                seeds.append(top_played.pop(random.randint(0,len(top_played)-1))["uri"])
            nextsong = sp.recommendations(seed_tracks = seeds, limit=1)["tracks"][0]
            return_obj = {"uri": nextsong["uri"], "upvotes": 0}

        else:
            return_obj = sorted(return_obj, reverse=True, key = lambda i: i["upvotes"])[0]
            setlist_db[publicID].update_one({"_id": return_obj.pop("_id")}, {"$set":{"played": 1}})
            session_db.update_one({"privateID": form["privateID"]}, {"$set":{"lastaccessed": now, "lastmodified":now}})

    if form["req"] == "setlist":
        form["number"] = int(form["number"])
        return_obj = list(setlist_db[form["publicID"]].find({"played": 0},{"_id": 0}))
        return_obj = sorted(return_obj, reverse=True, key = lambda i: i["upvotes"])
        return_obj = return_obj if form["number"] > len(return_obj) else return_obj[:form["number"]]
        session_db.update_one({"publicID": form["publicID"]}, {"$set":{"lastaccessed": now, "lastread":now}})
    if form["req"] == "updates":
        now = int(time.time())
        session = session_db.find_one({"publicID": form["publicID"]})
        return_obj = {"update": session["lastmodified"] > now - 7}
        session_db.update_one({"publicID": form["publicID"]}, {"$set":{"lastaccessed": now, "lastread":now}})
    if form["req"] == "public":
        session_db.update_one({"privateID": form["privateID"]}, {"$set":{"lastaccessed": now, "lastread":now}})
        info = session_db.find_one({"privateID": form["privateID"]})
        return_obj = {"publicID": info["publicID"], "display": info["display"]}
    if(form["req"] == "vote"):
        guestID = form["guestID"]
        session_info = session_db.find_one({"publicID": form['publicID']},{"_id":0})
        hancock = Signer(secret_key, salt=session_info['privateID'])
        if(not hancock.validate(guestID)):
            abort(401)
        publicID = form["publicID"]
        uri = form["uri"]
        direction = form["direction"]

        entry = setlist_db[publicID].find_one({"played": 0, "uri": uri})
        entry["upvoters"] = [] if "upvoters" not in entry.keys() else entry["upvoters"]
        entry["downvoters"] = [] if "downvoters" not in entry.keys() else entry["downvoters"]
        print(guestID)
        if direction == "up":
            if guestID in entry["downvoters"]:
                entry["downvoters"].remove(guestID)
            # if guestID in entry["upvoters"]:
            #     entry["upvoters"].remove(guestID)
            if guestID not in entry["upvoters"]:
                entry["upvoters"].append(guestID)
        if direction == "down":
            if guestID in entry["upvoters"]:
                entry["upvoters"].remove(guestID)
            # if guestID in entry["downvoters"]:
            #     entry["downvoters"].remove(guestID)
            if guestID not in entry["downvoters"]:
                entry["downvoters"].append(guestID)
        if direction == "neutral":
            if guestID in entry["upvoters"]:
                entry["upvoters"].remove(guestID)
            if guestID in entry["downvoters"]:
                entry["downvoters"].remove(guestID)

        entry["upvotes"] = len(entry["upvoters"]) - len(entry["downvoters"])
        print(entry["upvoters"])
        print(entry["downvoters"])
        setlist_db[publicID].update_one({"_id": entry["_id"]}, {"$set":entry})
        session_db.update_one({"publicID": form["publicID"]}, {"$set":{"lastaccessed": now, "lastmodified":now}})

    if(form["req"] == "submit"):
        guestID = form["guestID"]
        session_info = session_db.find_one({"publicID": form['publicID']},{"_id":0})
        hancock = Signer(secret_key, salt=session_info['privateID'])
        if(not hancock.validate(guestID)):
            abort(401)
        publicID = form["publicID"]
        uri = form["uri"]
        entry = setlist_db[publicID].find_one({"played": 0, "uri": uri})
        if(entry is not None): #if the song is already in the setlist:
            entry["upvoters"] = [] if "upvoters" not in entry.keys() else entry["upvoters"]
            entry["downvoters"] = [] if "downvoters" not in entry.keys() else entry["downvoters"]
            if guestID in entry["downvoters"]:
                entry["downvoters"].remove(guestID)
            if guestID not in entry["upvoters"]:
                entry["upvoters"].append(guestID)
            entry["upvotes"] = len(entry["upvoters"]) - len(entry["downvoters"])
            setlist_db[publicID].update_one({"_id": entry["_id"]}, {"$set":entry})
        else:
            return_obj = {"uri": uri, "upvoters":[guestID], "downvoters": [], "played": 0, "upvotes": 1}
            setlist_db[publicID].insert_one(return_obj)
            return_obj.pop("_id")
        session_db.update_one({"publicID": form["publicID"]}, {"$set":{"lastaccessed": now, "lastmodified":now}})
        # session_db.update_one({"publicID": publicID}, {"$set":{"lastaccessed": now, "lastmodified":now}})

    # print('request:', form)
    # print("response:", return_obj)
    return jsonify(return_obj)

# REMOVE THESE BEFORE LAUNCH

@app.route('/setlist/<string:publicID>')
def setlist(publicID):
    setlist = list(setlist_db[publicID].find({},{"_id":0}))
    if(setlist is None):
        return(woops(404));
    else:
        return jsonify(setlist)

@app.route('/sessions/')
def sessionlist():
    sessions = list(session_db.find())
    if(sessions is None):
        return(woops(404));
    else:
        return jsonify(sessions)

@app.route("/purge/")
def purgeDB():
    sess = session_db.find()
    sess = [x for x in sess] if sess is not None else sess
    [setlist_db[s["publicID"]].drop() for s in sess]
    session_db.drop()
    return jsonify(sess)

@app.route("/panic/<int:err>")
def panic(err):
    abort(err)

@app.errorhandler(404)
def woops(error):
    error = str(error);
    err = int(error[:3]) if error[:3].isdigit() else 503
    msg = error[4:error.find(":")] if error[:3].isdigit() else "Internal Error"
    return render_template("err.html", err = err, message = msg, exception = error), err
