"""
Low level access library for the bunq API

Features:
- Optimized for use in Google AppEngine
- Uses the Google Cloud Datastore for credentials (no files are used)
- Implements in-memory caching of credentials for optimal performance

Caveat: for use with one API key only per installation. This module does not
handle multiple API keys!
"""
# pylint: disable=dangerous-default-value

import base64
import json
import re
import secrets
import traceback

import requests

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import storage

NAME = "bunq2IFTTT"


# Core request methods
#----------------------

def get(endpoint, config={}):
    """ Send a GET request to bunq """
    return session_request('GET', endpoint, config)

def post(endpoint, data, config={}):
    """ Send a POST request to bunq """
    return session_request('POST', endpoint, config, data)

def put(endpoint, data, config={}):
    """ Send a PUT request to bunq """
    return session_request('PUT', endpoint, config, data)

def delete(endpoint, config={}):
    """ Send a DELETE request to bunq """
    return session_request('DELETE', endpoint, config)


# Handle installation / registration of the API key
#---------------------------------------------------

def install(token, name=NAME, allips=False, urlroot=None, mode=None):
    """ Handles the installation and registration of the API key """
    try:
        oldconfig = {}
        retrieve_config(oldconfig)

        config = {"access_token": token, "mode": mode}
        if "permissions" in oldconfig:
            config["permissions"] = oldconfig["permissions"]

        if "private_key" not in config:
            generate_key(config)
            install_key(config)

        register_token(config, name, allips)
        retrieve_userid(config)
        retrieve_accounts(config)
        save_config(config)

        if urlroot is not None:
            register_callback(config, urlroot)

        # Unregister only when the user_id has changed (i.e. when using OAuth)
        if urlroot is not None and "user_id" in oldconfig \
                               and oldconfig["user_id"] != config["user_id"]:
            unregister_callback(oldconfig)

        return config

    except:
        traceback.print_exc()
        raise


def generate_key(config):
    """ Generate a private/public keypair to communicate with the bunq API """
    print("[bunq] Generating new private key...")
    my_private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    my_private_key_enc = str(my_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ), encoding='ascii')

    my_public_key = my_private_key.public_key()
    my_public_key_enc = str(my_public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ), encoding='ascii')

    config["private_key"] = my_private_key
    config["private_key_enc"] = my_private_key_enc
    config["public_key"] = my_public_key
    config["public_key_enc"] = my_public_key_enc


def install_key(config):
    """ Install the generated private/public keypair with bunq """
    print("[bunq] Installing key...")
    data = {"client_public_key": config["public_key_enc"]}
    result = post("v1/installation", data, config)

    install_token = result["Response"][1]["Token"]["token"]
    srv_key = result["Response"][2]["ServerPublicKey"]["server_public_key"]

    config["install_token"] = install_token
    config["server_key_enc"] = srv_key
    config["server_key"] = serialization.load_pem_public_key(
        srv_key.encode("ascii"), backend=default_backend())


def register_token(config, name, allips):
    """ Register the provided access token with bunq """
    print("[bunq] Registering token...")
    if allips:
        ips = ["*"]
    else:
        ips = [requests.get("https://api.ipify.org").text]
    data = {"description": name,
            "secret": config["access_token"],
            "permitted_ips": ips}
    post("v1/device-server", data, config)


def retrieve_userid(config):
    """ Retrieve the userid that needs to be used in api calls """
    print("[bunq] Retrieving userid...")
    result = get("v1/user", config)
    for user in result["Response"]:
        for typ in user:
            userid = user[typ]["id"]
            config["user_id"] = userid


_TYPE_TRANSLATION = {
    "MonetaryAccountBank": "monetary-account-bank",
    "MonetaryAccountJoint": "monetary-account-joint",
    "MonetaryAccountSavings": "monetary-account-savings",
}

def retrieve_accounts(config):
    """ Retrieve the set of accounts of the user """
    print("[bunq] Retrieving accounts...")
    config["accounts"] = []
    result = get("v1/user/{}/monetary-account".format(config["user_id"]),
                 config)
    for res in result["Response"]:
        for typ in res:
            acc = res[typ]
            type_url = _TYPE_TRANSLATION[typ]
        if acc["status"] == "ACTIVE":
            iban = None
            for alias in acc["alias"]:
                if alias["type"] == "IBAN":
                    iban = alias["value"]
                    name = alias["name"]
            accinfo = {"iban": iban,
                       "name": name,
                       "type": type_url,
                       "id": acc["id"],
                       "description": acc["description"]}
            config["accounts"].append(accinfo)


def register_callback(config, urlroot):
    """ Register the callbacks on the account """
    print("[bunq] Set notification filters...")
    post("v1/user/{}/notification-filter-url".format(config["user_id"]), {
        "notification_filters": [{
            "category": "MUTATION",
            "notification_target": urlroot + "/bunq2ifttt_mutation"
        }, {
            "category": "REQUEST",
            "notification_target": urlroot + "/bunq2ifttt_request"
        }]
    }, config)


def unregister_callback(config):
    """ Remove old callbacks when reauthorizing """
    print("[bunq] Removing old notification filters...")
    old = get("v1/user/{}/notification-filter-url".format(config["user_id"]),
              config)
    new = {"notification_filters": []}
    if "notification_filters" in old:
        for noti in old["notification_filters"]:
            if not noti["notification_target"].endswith("bunq2ifttt_mutation")\
            and not noti["notification_target"].endswith("bunq2ifttt_request"):
                new["notification_filters"].append(noti)
    print("old: "+json.dumps(old))
    print("new: "+json.dumps(new))
    post("v1/user/{}/notification-filter-url".format(config["user_id"]),
         new, config)


# Credentials retrieval
#-----------------------------------

def save_config(config):
    """ Save the configuration parameters """
    tosave = {}
    for key in config:
        # Only store supported types
        if isinstance(config[key], (str, int, float, dict, list))\
        or config[key] is None:
            tosave[key] = config[key]
    storage.store_large("bunq2IFTTT", "bunq_config", tosave)

def retrieve_config(config={}):
    """ Retrieve the configuration parameters from storage """
    for key in list(config.keys()):
        del config[key]
    toload = storage.get_value("bunq2IFTTT", "bunq_config")
    if toload is not None:
        for key in toload:
            config[key] = toload[key]
    # Convert strings back to keys
    if "server_key_enc" in config:
        config["server_key"] = serialization.load_pem_public_key(
            config["server_key_enc"].encode("ascii"),
            backend=default_backend())
    if "public_key_enc" in config:
        config["public_key"] = serialization.load_pem_public_key(
            config["public_key_enc"].encode("ascii"),
            backend=default_backend())
    if "private_key_enc" in config:
        config["private_key"] = serialization.load_pem_private_key(
            config["private_key_enc"].encode("ascii"),
            password=None, backend=default_backend())
    return config


def get_session_token(config):
    """ Return the session token, create or retrieve from storage if needed """
    if "private_key" not in config:
        retrieve_config(config)
    if "session_token" not in config:
        refresh_session_token(config)
    return config["session_token"]

def get_access_token(config):
    """ Return the access token, retrieve from storage if needed """
    if "access_token" not in config:
        retrieve_config(config)
    return config["access_token"]

def get_install_token(config):
    """ Return the install token, retrieve from storage if needed """
    if "install_token" not in config:
        retrieve_config(config)
    return config["install_token"]

def get_server_key(config):
    """ Return the server public key, retrieve from storage if needed """
    if "server_key" not in config:
        retrieve_config(config)
    return config["server_key"]

def get_private_key(config):
    """ Return the my private key, retrieve from storage if needed """
    if "private_key" not in config:
        retrieve_config(config)
    return config["private_key"]

def get_public_key(config):
    """ Return the my public key, retrieve from storage if needed """
    if "public_key" not in config:
        retrieve_config(config)
    return config["public_key"]


# Deal with session key expiration
#----------------------------------

def session_request(method, endpoint, config, data=None, extra_headers=None):
    """ Send a request, refreshing session keys if needed """
    result = request(method, endpoint, config, data, extra_headers)
    if isinstance(result, dict) and "Error" in result and \
            result["Error"][0]["error_description"] in \
            ["Insufficient authorisation.", "Insufficient authentication."]:
        refresh_session_token(config)
        result = request(method, endpoint, config, data, extra_headers)
    return result

def refresh_session_token(config):
    """ Refresh an expired session token """
    print("[bunq] Refreshing session token...")
    data = {"secret": get_access_token(config)}
    result = post("v1/session-server", data, config)
    if "Response" in result:
        session_token = result["Response"][1]["Token"]["token"]
        config["session_token"] = session_token
        save_config(config)
        return session_token
    print("ERROR: session token refresh failed!")
    print(result)
    return ""

def session_request_encrypted(method, endpoint, data, config={}):
    """ Send an encrypted request to the bunq API """
    data = json.dumps(data).encode("utf-8")
    padding_length = (16 - len(data) % 16)
    padding_character = bytes(bytearray([padding_length]))
    data = data + padding_character * padding_length

    inv = secrets.token_bytes(16)
    key = secrets.token_bytes(32)

    encryptor = Cipher(algorithms.AES(key), modes.CBC(inv),
                       backend=default_backend()).encryptor()
    ctx = encryptor.update(data) + encryptor.finalize()

    enc = get_server_key(config).encrypt(key, padding.PKCS1v15())

    hmc = hmac.HMAC(key, hashes.SHA1(), backend=default_backend())
    hmc.update(inv + ctx)
    hmc = hmc.finalize()
    headers = {
        'X-Bunq-Client-Encryption-Iv': base64.b64encode(inv).decode("ascii"),
        'X-Bunq-Client-Encryption-Key': base64.b64encode(enc).decode("ascii"),
        'X-Bunq-Client-Encryption-Hmac': base64.b64encode(hmc).decode("ascii"),
    }
    return session_request(method, endpoint, config, ctx, headers)


# Internal request methods - do not call directly
#-------------------------------------------------

BUNQAPI = "https://api.bunq.com/"

def request(method, endpoint, config, data=None, extra_headers=None):
    """ This method executes the actual request to the bunq API """
    print(method, endpoint)
    if data is None:
        data = ""
    elif not isinstance(data, bytes):
        data = json.dumps(data)
    headers = {
        'Cache-Control': 'no-cache',
        'User-Agent': NAME,
    }
    if extra_headers is not None:
        for extra in extra_headers:
            headers[extra] = extra_headers[extra]
    if endpoint in ["v1/device-server", "v1/session-server"]:
        headers['X-Bunq-Client-Authentication'] = get_install_token(config)
    elif endpoint != "v1/installation":
        headers['X-Bunq-Client-Authentication'] = get_session_token(config)
    sign(endpoint, config, headers, data)
    if method == "GET":
        reply = requests.get(BUNQAPI + endpoint, headers=headers)
    elif method == "POST":
        reply = requests.post(BUNQAPI + endpoint, headers=headers, data=data)
    elif method == "PUT":
        reply = requests.put(BUNQAPI + endpoint, headers=headers, data=data)
    elif method == "DELETE":
        reply = requests.delete(BUNQAPI + endpoint, headers=headers)
    if reply.status_code == 500 and re.match(r"v1/user/\d+/card/\d+",
                                             endpoint):
        print("Ignoring error 500 for card update")
        return "OK" # work around a bug where the bunq API returns status 500
                    # on a card account update, even though the call succeeded
    verify(endpoint, config, reply.status_code, reply.headers, reply.text)
    if reply.headers["Content-Type"] == "application/json":
        return reply.json()
    return reply.text

def sign(endpoint, config, headers, data):
    """ Sign the message before sending """
    if endpoint == "v1/installation":
        return # Installation call is not signed
    message = data.encode("ascii")
    key = get_private_key(config)
    sig = key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    sig_str = base64.b64encode(sig).decode("ascii")
    headers['X-Bunq-Client-Signature'] = sig_str

def verify(endpoint, config, status_code, headers, text):
    """ Verify bunq's signature on the reply """
    if endpoint == "v1/installation":
        return # Installation call is not signed
    if headers["Content-Type"] == "application/json":
        result = json.loads(text)
        if "Error" in result:
            print(result)
            return # Errors are not signed

    sig = base64.b64decode(headers["X-Bunq-Server-Signature"])
    key = get_server_key(config)
    try: # try new body signing first
        key.verify(sig, text.encode("ascii"),
                   padding.PKCS1v15(), hashes.SHA256())

    except InvalidSignature: # fall back to old signing
        print("Fallback to old signature verification method")
        message = str(status_code) + "\n"
        for name in sorted(headers.keys()):
            if name[:7] == "X-Bunq-" and name != "X-Bunq-Server-Signature":
                message += name + ": " + headers[name] + "\n"
        message += "\n" + text
        try:
            key.verify(sig, message.encode("ascii"),
                       padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature:
            print("WARNING: signature verification failed!")
