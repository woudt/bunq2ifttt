"""
Low level access library for the bunq API

Features:
- Optimized for use in Google AppEngine
- Uses the Google Cloud Datastore for credentials (no files are used)
- Implements in-memory caching of credentials for optimal performance

Caveat: for use with one API key only per installation. This module does not
handle multiple API keys!
"""
# pylint: disable=global-statement

import base64
import json
import traceback

import requests

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import storage

NAME = "bunq2IFTTT"


# Core request methods
#----------------------

def get(endpoint):
    """ Send a GET request to bunq """
    return session_request('GET', endpoint)

def post(endpoint, data):
    """ Send a POST request to bunq """
    return session_request('POST', endpoint, data)

def put(endpoint, data):
    """ Send a PUT request to bunq """
    return session_request('PUT', endpoint, data)

def delete(endpoint):
    """ Send a DELETE request to bunq """
    return session_request('DELETE', endpoint)


# Handle installation / registration of the API key
#---------------------------------------------------

def install(token, name=NAME, allips=False):
    """ Handles the installation and registration of the API key

    Args:
        token (str): the API key as provided by the app or the token returned
                     from the OAuth token exchange (by calling the v1/token)
    """
    global _ACCESS_TOKEN, _INSTALL_TOKEN, _SESSION_TOKEN, \
           _SERVER_KEY, _PRIVATE_KEY
    try:
        _ACCESS_TOKEN = token
        print("[bunq] Generating new private key...")
        _PRIVATE_KEY = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        print("[bunq] Installing key...")
        data = {"client_public_key": get_public_key()}
        result = post("v1/installation", data)
        _INSTALL_TOKEN = result["Response"][1]["Token"]["token"]
        _server_bytes = result["Response"][2]["ServerPublicKey"] \
            ["server_public_key"].encode("ascii")
        _SERVER_KEY = serialization.load_pem_public_key(
            _server_bytes, backend=default_backend())

        print("[bunq] Registering token...")
        if allips:
            ips = ["*"]
        else:
            ips = [requests.get("https://api.ipify.org").text]
        data = {"description": name,
                "secret": _ACCESS_TOKEN,
                "permitted_ips": ips}
        result = post("v1/device-server", data)

        _private_bytes = _PRIVATE_KEY.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        # split to fit within 1500 byte maximum
        private_1 = _private_bytes[:1000]
        private_2 = _private_bytes[1000:]

        storage.store("config", "bunq_private_key_1", {"value": \
            base64.a85encode(private_1).decode("ascii")})
        storage.store("config", "bunq_private_key_2", {"value": \
            base64.a85encode(private_2).decode("ascii")})
        storage.store("config", "bunq_server_key", {"value": \
            base64.a85encode(_server_bytes).decode("ascii")})
        storage.store("config", "bunq_access_token", {"value": \
            _ACCESS_TOKEN})
        storage.store("config", "bunq_install_token", {"value": \
            _INSTALL_TOKEN})

        _SESSION_TOKEN = None

    except:
        traceback.print_exc()
        _ACCESS_TOKEN = None
        _INSTALL_TOKEN = None
        _SERVER_KEY = None
        _PRIVATE_KEY = None
        _SESSION_TOKEN = None
        raise


# Credentials cashing and retrieval
#-----------------------------------

_SESSION_TOKEN = None
_ACCESS_TOKEN = None
_INSTALL_TOKEN = None
_SERVER_KEY = None
_PRIVATE_KEY = None


def get_session_token(force=False):
    """ Retrieves the session token from cache or the datastore
        or get one from the server if it is the first time
    """
    global _SESSION_TOKEN
    if force:
        refresh_session_token()
    elif _SESSION_TOKEN is None:
        entity = storage.retrieve("config", "bunq_session_token")
        if entity is not None:
            _SESSION_TOKEN = entity["value"]
        else:
            refresh_session_token()
    return _SESSION_TOKEN

def get_access_token():
    """ Retrieves the access token from cache or the datastore """
    global _ACCESS_TOKEN
    if _ACCESS_TOKEN is None:
        entity = storage.retrieve("config", "bunq_access_token")
        _ACCESS_TOKEN = entity["value"]
    return _ACCESS_TOKEN

def get_install_token():
    """ Retrieves the install token from cache or the datastore """
    global _INSTALL_TOKEN
    if _INSTALL_TOKEN is None:
        entity = storage.retrieve("config", "bunq_install_token")
        _INSTALL_TOKEN = entity["value"]
    return _INSTALL_TOKEN

def get_server_key():
    """ Retrieves the server public key from cache or the datastore """
    global _SERVER_KEY
    if _SERVER_KEY is None:
        entity = storage.retrieve("config", "bunq_server_key")
        server_bytes = base64.a85decode(entity["value"])
        _SERVER_KEY = serialization.load_pem_public_key(
            server_bytes, backend=default_backend())
    return _SERVER_KEY

def get_private_key():
    """ Retrieves my private key from cache or the datastore """
    global _PRIVATE_KEY
    if _PRIVATE_KEY is None:
        entity = storage.retrieve("config", "bunq_private_key_1")
        private_1 = base64.a85decode(entity["value"])
        entity = storage.retrieve("config", "bunq_private_key_2")
        private_2 = base64.a85decode(entity["value"])
        _PRIVATE_KEY = serialization.load_pem_private_key(
            private_1 + private_2, password=None, backend=default_backend())
    return _PRIVATE_KEY

def get_public_key():
    """ Retrieves my public key in ascii format """
    return str(get_private_key().public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ), encoding='ascii')


# Deal with session key expiration
#----------------------------------

def session_request(method, endpoint, data=None):
    """ Send a request, refreshing session keys if needed """
    oldtoken = _SESSION_TOKEN
    result = request(method, endpoint, data)
    # This handles an edge case where multiple instances of this code are
    # active and this one has an out of date session key in memory
    if isinstance(result, dict) and "Error" in result and \
            result["Error"][0]["error_description"] in \
            ["Insufficient authorisation.", "Insufficient authentication."]:
        newtoken = get_session_token(force=True)
        if oldtoken is not None and newtoken != oldtoken:
            result = request(method, endpoint, data)
    # This handles the normal case, where the session token has expired and
    # needs to be refreshed
    if isinstance(result, dict) and "Error" in result and \
            result["Error"][0]["error_description"] in \
            ["Insufficient authorisation.", "Insufficient authentication."]:
        refresh_session_token()
        result = request(method, endpoint, data)
    return result

def refresh_session_token():
    """ Refresh an expired session token """
    global _SESSION_TOKEN
    print("[bunq] Refreshing session token...")
    data = {"secret": get_access_token()}
    result = post("v1/session-server", data)
    if "Response" in result:
        _SESSION_TOKEN = result["Response"][1]["Token"]["token"]
        storage.store("config", "bunq_session_token", {"value": \
            _SESSION_TOKEN})


# Internal request methods - do not call directly
#-------------------------------------------------

BUNQAPI = "https://api.bunq.com/"

def request(method, endpoint, data=None):
    """ This method executes the actual request to the bunq API """
    print(method, endpoint)
    data = json.dumps(data) if data else ""
    headers = {
        'Cache-Control': 'no-cache',
        'User-Agent': NAME,
        'X-Bunq-Client-Request-Id': '0',
        'X-Bunq-Geolocation': '0 0 0 0 000',
        'X-Bunq-Language': 'en_US',
        'X-Bunq-Region': 'en_US',
    }
    if endpoint in ["v1/device-server", "v1/session-server"]:
        headers['X-Bunq-Client-Authentication'] = get_install_token()
    elif endpoint != "v1/installation":
        headers['X-Bunq-Client-Authentication'] = get_session_token()
    sign(method, endpoint, headers, data)
    if method == "GET":
        reply = requests.get(BUNQAPI + endpoint, headers=headers)
    elif method == "POST":
        reply = requests.post(BUNQAPI + endpoint, headers=headers, data=data)
    elif method == "PUT":
        reply = requests.put(BUNQAPI + endpoint, headers=headers, data=data)
    elif method == "DELETE":
        reply = requests.delete(BUNQAPI + endpoint, headers=headers)
    verify(endpoint, reply.status_code, reply.headers, reply.text)
    if reply.headers["Content-Type"] == "application/json":
        return reply.json()
    return reply.text

def sign(method, endpoint, headers, data):
    """ Sign the message before sending """
    if endpoint == "v1/installation":
        return # Installation call is not signed
    message = method + " /" + endpoint + "\n"
    for name in sorted(headers.keys()):
        message += name + ": " + headers[name] + "\n"
    message += "\n" + data
    key = get_private_key()
    sig = key.sign(message.encode("ascii"), padding.PKCS1v15(),
                   hashes.SHA256())
    sig_str = base64.b64encode(sig).decode("ascii")
    headers['X-Bunq-Client-Signature'] = sig_str

def verify(endpoint, status_code, headers, text):
    """ Verify bunq's signature on the reply """
    if endpoint == "v1/installation":
        return # Installation call is not signed
    if headers["Content-Type"] == "application/json":
        result = json.loads(text)
        if "Error" in result:
            print(result)
            return # Errors are not signed
    message = str(status_code) + "\n"
    for name in sorted(headers.keys()):
        if name.startswith("X-Bunq-") and name != "X-Bunq-Server-Signature":
            message += name + ": " + headers[name] + "\n"
    message += "\n" + text
    sig = base64.b64decode(headers["X-Bunq-Server-Signature"])
    key = get_server_key()
    # Will throw an exception on failure
    key.verify(sig, message.encode("ascii"),
               padding.PKCS1v15(), hashes.SHA256())
