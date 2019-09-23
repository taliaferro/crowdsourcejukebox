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
import requests

import pymongo
from flask_pymongo import PyMongo
from bson.json_util import dumps

import spotipy
import spotipy.util as util
from spotipy.oauth2 import SpotifyClientCredentials

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
    adj1 = linecache.getline('other/adjectives.txt', random.randint(1,243)).strip()
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
    toinsert["guests"] = 1
    toinsert["settings"] = {"noexplicit": False, "songlimit": False, "voteoff": False, "captcha": False}
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

flaskpymongo=PyMongo(app, uri=os.environ["MONGO_URI"])
mclient = flaskpymongo.cx
setlist_db = mclient["setlists"]
session_db = mclient["meta"]["sessions"]

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
    session_info = session_db.find_one({"publicID": publicID},{"_id":0})
    if session_info is None:
        abort(404)
    session_db.update_one({"publicID": publicID}, {"$set":{"lastaccessed": now, "lastread":now}})
    current_playlist = list(setlist_db[publicID].find({"played": 0}, {"_id":0}).sort("upvotes", -1))

    if current_playlist != []:
        tmp_playlist = current_playlist
        tracks = []
        while(len(tmp_playlist)>=50):
            tracks += sp.tracks([x["uri"] for x in tmp_playlist[:50]])["tracks"]
            tmp_playlist = tmp_playlist[50:]
        tracks += sp.tracks([x["uri"] for x in tmp_playlist])["tracks"]

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
        # print(session_info["settings"], file=sys.stderr)
        if(session_info['settings']["captcha"]):
            return redirect("https://www.crowdsourcejukebox.com/captcha/"+publicID+"/")
        else:
            guestID = bytes(str(uuid.uuid4()), "utf-8")
            session_db.update_one({"publicID": publicID}, {"$inc": {"guests": 1}})
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
        return redirect("http://www.csjb.cc/" + publicID)
    else:
        if(not hancock.validate(request.cookies.get(publicID + "-guest"))):
            abort(401)

    query = request.query_string.decode("UTF-8")
    if(query != "" and "query=" in query):
        query = query[query.index('query='):]
        query = query[query.index('=')+1:]
        query = query if "&" not in query else query[:query.index("&")]
        if(query == ""):
            return render_template("search.html", publicID=publicID)
        query = urllib.parse.unquote_plus(query)
        results = sp.search(query, limit=35)["tracks"]["items"]
        if(session_info["settings"]["noexplicit"]):
            results = [x for x in results if not x["explicit"]]
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

def is_human(captcha_response):
    """ Validating recaptcha response from google server
        Returns True captcha test passed for submitted form else returns False.
    """
    secret = os.environ["RC_SECRET_KEY"]
    payload = {'response':captcha_response, 'secret':secret}
    response = requests.post("https://www.google.com/recaptcha/api/siteverify", payload)
    response_text = json.loads(response.text)
    # print(response.text, file=sys.stderr)
    return response_text['success']

@app.route("/captcha/<string:publicID>/", methods=["POST", "GET"])
def captcha(publicID):
    publicID = publicID.lower()

    session_info = session_db.find_one({"publicID": publicID},{"_id":0})
    hancock = Signer(str(secret_key), salt=str(session_info['privateID']))

    if(publicID + "-guest") in request.cookies and hancock.validate(request.cookies.get(publicID + "-guest")):
        return redirect("https://www.crowdsourcejukebox.com/vote/" + publicID + "/")

    if request.method == "POST":
        captcha_response = request.form['g-recaptcha-response']
        if is_human(captcha_response):
            resp = make_response(redirect("https://www.crowdsourcejukebox.com/vote/" + publicID + "/"))
            guestID = bytes(str(uuid.uuid4()), "utf-8")
            session_db.update_one({"publicID": publicID}, {"$inc": {"guests": 1}})
            resp.set_cookie(publicID + "-guest",
                            value=hancock.sign(guestID),
                            expires=datetime.datetime.now() + datetime.timedelta(hours=1))
            return resp
        else:
            return redirect("http://www.crowdsourcejukebox.com/")
    else:
        return render_template("captcha.html", sitekey = os.environ["RC_SITE_KEY"])


# UTILITY ROUTES

@app.route('/api/', methods=['POST'])
def api():
    now = int(time.time())
    form = {key:request.form[key] for key in request.form.keys()}
    authorized_requests = ["newID",
                           "unload",
                           "setlist",
                           "updates",
                           "public",
                           "playnext",
                           "vote",
                           "submit",
                           "settings",
                           "setFallback"]
    if "req" not in form.keys() or form["req"] not in authorized_requests:
        abort(400)

    print('request:', form, file=sys.stderr)
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
                top_played = top_played[:int(len(top_played)/2)]
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
        # print("session", file=sys.stderr)
        # print(session, file=sys.stderr)
        # print("session", file=sys.stderr)
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
        # print(guestID)
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
        # print(entry["upvoters"])
        # print(entry["downvoters"])
        if len(entry["downvoters"]) > int(0.6 * session_info["guests"]):
             setlist_db[publicID].delete_one({"_id": entry["_id"]})
        else:
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
            return_obj = {"uri": uri, "upvoters":[guestID], "downvoters": [], "submitted_by": guestID, "played": 0, "upvotes": 1}
            setlist_db[publicID].insert_one(return_obj)
            return_obj.pop("_id")
        session_db.update_one({"publicID": form["publicID"]}, {"$set":{"lastaccessed": now, "lastmodified":now}})
        # session_db.update_one({"publicID": publicID}, {"$set":{"lastaccessed": now, "lastmodified":now}})

    if(form["req"] == "settings"):
        # print(str(form), file=sys.stderr)
        session_info = session_db.find_one({"privateID": form['privateID']},{"_id":0})
        if(session_info is None):
            abort(404)
        settings = {"noexplicit": form["noexplicit"] == "true","songlimit": form["songlimit"]== "true","voteoff": form["voteoff"]== "true","captcha": form["captcha"]== "true",}
        # print(settings, file=sys.stderr)
        session_db.update_one({"privateID": form["privateID"]}, {"$set":{"lastaccessed": now, "lastmodified":now, "settings": settings}})
        return_obj = session_db.find_one({"privateID": form['privateID']},{"_id":0})
        if(settings["noexplicit"]):
            tmp_playlist = list(setlist_db[session_info["publicID"]].find({"played": 0}, {"_id":0}).sort("upvotes", -1))
            tracks = []
            while(len(tmp_playlist)>=50):
                tracks += sp.tracks([x["uri"] for x in tmp_playlist[:50]])["tracks"]
                tmp_playlist = tmp_playlist[50:]
            tracks += sp.tracks([x["uri"] for x in tmp_playlist])["tracks"]
            tracks = [t["uri"] for t in tracks if t["explicit"]]

            setlist_db[session_info["publicID"]].delete_many({"uri":{"$in": tracks}})
    if(form["req"] == "setFallback"):
        session_info = session_db.find_one({"privateID": form['privateID']},{"_id":0})
        if(session_info is None):
            abort(404)
        setlist_db[session_info['publicID']].delete_many({"submitted_by": "fallback"})
        to_insert = sp.user_playlist(form["user"], form["uri"])['tracks']['items']
        if(session_info["settings"]["noexplicit"]):
            for track in to_insert:
                # print(track["track"], file=sys.stderr)
                if(track["track"]["explicit"]):
                    to_insert.remove(track)
        to_insert = [{"uri": x['track']['uri'], "upvotes": 0, "submitted_by": "fallback", "upvoters":[], "downvoters":[], "played": 0} for x in to_insert]
        # return_obj = to_insert
        setlist_db[session_info['publicID']].insert_many(to_insert)
        session_db.update_one({"privateID": form["privateID"]}, {"$set":{"lastaccessed": now, "lastmodified":now}})
        # return_obj.pop("_id")

    print("response:", return_obj, file=sys.stderr)
    return jsonify(return_obj)

# REMOVE THESE BEFORE LAUNCH

# @app.route('/setlist/<string:publicID>')
# def setlist(publicID):
#     setlist = list(setlist_db[publicID].find({},{"_id":0}))
#     if(setlist is None):
#         return(woops(404));
#     else:
#         return jsonify(setlist)
#
# @app.route('/sessions/')
# def sessionlist():
#     sessions = list(session_db.find())
#     if(sessions is None):
#         return(woops(404));
#     else:
#         return jsonify(sessions)
#
# @app.route("/purge/")
# def purgeDB():
#     sess = session_db.find()
#     sess = [x for x in sess] if sess is not None else sess
#     [setlist_db[s["publicID"]].drop() for s in sess]
#     session_db.drop()
#     return jsonify(sess)

@app.route("/panic/<int:err>")
def panic(err):
    abort(err)

@app.errorhandler(404)
def woops(error):
    error = str(error);
    err = int(error[:3]) if error[:3].isdigit() else 503
    msg = error[4:error.find(":")] if error[:3].isdigit() else "Internal Error"
    return render_template("err.html", err = err, message = msg, exception = error), err
