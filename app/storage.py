"""
Abstraction layer for storage

Depending on whether the application is run in appengine or standalone,
it will select:
- Google datastore storage
- Local storage in the db/ directory
"""

import json
import os
import threading
import time
import traceback

if os.getenv("GAE_INSTANCE") is not None:
    # Used in Google Appengine, so use Google datastore
    from google.cloud import datastore
    DSCLIENT = datastore.Client()
    USE_GOOGLE_DATASTORE = True
else:
    # Use local datastore
    USE_GOOGLE_DATASTORE = False

LOCK = threading.Lock()


def query_indexes(kind):
    """ Query all indexes for the given kind """
    if USE_GOOGLE_DATASTORE:
        result = []
        qry = DSCLIENT.query(kind=kind)
        qry.keys_only()
        for entity in qry.fetch():
            result.append(entity.key.id_or_name)
    else:
        fname = "db" + os.sep + str(kind) + os.sep
        try:
            result = os.listdir(fname)
        except FileNotFoundError:
            pass
    return result

def query_all(kind):
    """ Query all stored data of the given kind """
    result = []
    if USE_GOOGLE_DATASTORE:
        qry = DSCLIENT.query(kind=kind)
        for entity in qry.fetch():
            data = {'id': entity.key.id_or_name}
            for key in entity.keys():
                data[key] = json.loads(entity[key])
            result.append(data)
    else:
        base = "db" + os.sep + str(kind) + os.sep
        try:
            names = os.listdir(base)
        except FileNotFoundError:
            return result
        for fname in names:
            with open(base + fname) as fil:
                data = json.loads(fil.read())
                data['id'] = fname
                result.append(data)
    return result


def query(kind, label, comparator, value):
    """ Query stored data and return all that satisfy the given condition """
    result = []
    if USE_GOOGLE_DATASTORE:
        qry = DSCLIENT.query(kind=kind)
        qry.add_filter(label, comparator, json.dumps(value))
        for entity in qry.fetch():
            data = {'id': entity.key.id_or_name}
            for key in entity.keys():
                data[key] = json.loads(entity[key])
            result.append(data)
    else:
        base = "db" + os.sep + str(kind) + os.sep
        try:
            names = os.listdir(base)
        except FileNotFoundError:
            return result
        for fname in names:
            with open(base + fname) as fil:
                data = json.loads(fil.read())
                data['id'] = fname
            if comparator == "=" and data[label] == value:
                result.append(data)
            elif comparator == "<" and data[label] < value:
                result.append(data)
            elif comparator == "<=" and data[label] <= value:
                result.append(data)
            elif comparator == ">" and data[label] > value:
                result.append(data)
            elif comparator == ">=" and data[label] >= value:
                result.append(data)
    return result


def retrieve(kind, index):
    """ Retrieve a previously stored dict """
    index = str(index)
    if USE_GOOGLE_DATASTORE:
        key = DSCLIENT.key(kind, index)
        entity = DSCLIENT.get(key)
        if entity is None:
            return None
        result = {}
        for label in entity.keys():
            result[label] = json.loads(entity[label])
        return result
    fname = "db" + os.sep + str(kind) + os.sep + str(index)
    if os.path.isfile(fname):
        with open(fname) as fil:
            data = json.loads(fil.read())
            return data
    return None


def get_value(kind, index):
    """ Retrieve a previously stored value """
    data = retrieve(kind, index)
    if data is not None:
        data = data["value"]
    return data


def store(kind, index, value):
    """ Store a dict """
    index = str(index)
    if USE_GOOGLE_DATASTORE:
        entity = datastore.Entity(key=DSCLIENT.key(kind, index))
        for label in value:
            entity[label] = json.dumps(value[label])
        DSCLIENT.put(entity)
    else:
        fname = "db" + os.sep + str(kind)
        os.makedirs(fname, exist_ok=True)
        fname += os.sep + str(index)
        with open(fname, "w") as fil:
            fil.write(json.dumps(value))


def store_large(kind, index, value):
    """ Store a large (not indexed) value """
    index = str(index)
    if USE_GOOGLE_DATASTORE:
        entity = datastore.Entity(key=DSCLIENT.key(kind, index),
                                  exclude_from_indexes=['value'])
        entity["value"] = json.dumps(value)
        DSCLIENT.put(entity)
    else:
        fname = "db" + os.sep + str(kind)
        os.makedirs(fname, exist_ok=True)
        fname += os.sep + str(index)
        with open(fname, "w") as fil:
            fil.write(json.dumps({"value": value}))


def insert_value_maxsize(kind, index, value, maxsize):
    """ Add a value to the beginning of a stored array, keeping a given maximum
        number of records. """
    values = get_value(kind, index)
    if values is None:
        values = []
    values.insert(0, value)
    values = values[:maxsize]
    store_large(kind, index, values)


def remove(kind, index):
    """ Remove the given record """
    index = str(index)
    if USE_GOOGLE_DATASTORE:
        print("delete: ", kind, index)
        DSCLIENT.delete(DSCLIENT.key(kind, index))
    else:
        fname = "db" + os.sep + str(kind) + os.sep + str(index)
        os.remove(fname)
        try: # try removing empty directories
            os.removedirs(fname)
        except OSError:
            pass

# pylint: disable=bare-except
def seen(kind, index):
    """ Write a 'seen' object with a transaction/locking to ensure
        an object is only seen once. Returns True if seen before,
        False if this is the first time."""
    index = str(index)
    result = False
    if USE_GOOGLE_DATASTORE:
        retries = 2
        while retries > 0:
            retries -= 1
            try:
                result = seen_google(kind, index)
                break
            except:
                traceback.print_exc()
                print("Retries left: ", retries)
    else:
        LOCK.acquire()
        fname = "db" + os.sep + str(kind) + "." + str(index)
        if os.path.isfile(fname):
            result = True
        else:
            with open(fname, "w") as fil:
                fil.write(json.dumps({"timestamp": int(time.time())}))
        LOCK.release()
    return result
# pylint: enable=bare-except

def seen_google(kind, index):
    """ Helper method for the seen method above, used with google datastore """
    with DSCLIENT.transaction():
        seenkey = DSCLIENT.key(kind, index)
        entity = DSCLIENT.get(seenkey)
        if entity is not None:
            return True
        entity = datastore.Entity(key=seenkey)
        entity["timestamp"] = int(time.time())
        DSCLIENT.put(entity)
        return False

def clean_seen(kind):
    """ Clean up the seen index by removing all older than 15 minutes """
    target = int(time.time()) - 900
    if USE_GOOGLE_DATASTORE:
        qry = DSCLIENT.query(kind=kind)
        qry.add_filter("timestamp", "<", target)
        qry.keys_only()
        for entity in qry.fetch():
            DSCLIENT.delete(entity.key)
    else:
        fname = "db" + os.sep + str(kind) + os.sep
        try:
            names = os.listdir(fname)
        except FileNotFoundError:
            return
        for fname in names:
            with open(fname) as fil:
                data = json.loads(fil.read())
            if data["timestamp"] < target:
                os.remove(fname)
