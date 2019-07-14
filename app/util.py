"""
Utility methods

Mainly to handle storage and caching of some frequently used data elements
"""
# pylint: disable=global-statement

import base64
import json

import requests

from flask import request

import bunq
import storage

# Use global variables as in-memory cache mechanisms
_IFTTT_SERVICE_KEY = None
_BUNQ_ACCOUNTS_LOCAL = None
_BUNQ_ACCOUNTS_CALLBACK = None
_BUNQ_USERID = None
_BUNQ_SECURITY_MODE = None
_APP_MODE = None
_APP_MASTER_URL = None


# WARNING: the follow setting is extremely dangerous to change !!!!!!!!!!!!!!!!
# WARNING: you can loose all your money !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# WARNING: use at your own risk !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
def get_external_payment_enabled():
    """ Get whether external payments are enabled """
    return False


def get_session_cookie():
    """ Return the users session cookie """
    entity = storage.retrieve("config", "session_cookie")
    if entity is not None:
        return entity["value"]
    return None

def save_session_cookie(value):
    """ Save the users session cookie """
    storage.store("config", "session_cookie", {"value": value})


def get_ifttt_service_key():
    """ Return the IFTTT service key, used to secure IFTTT calls """
    global _IFTTT_SERVICE_KEY
    if _IFTTT_SERVICE_KEY is None:
        entity = storage.retrieve("config", "ifttt_service_key")
        if entity is not None:
            _IFTTT_SERVICE_KEY = entity["value"]
    return _IFTTT_SERVICE_KEY

def save_ifttt_service_key(value):
    """ Save the IFTTT service key, used to secure IFTTT calls """
    global _IFTTT_SERVICE_KEY
    _IFTTT_SERVICE_KEY = value
    storage.store("config", "ifttt_service_key", {"value": value})


def get_bunq_accounts_local():
    """ Return the list of bunq accounts with local access """
    global _BUNQ_ACCOUNTS_LOCAL
    if _BUNQ_ACCOUNTS_LOCAL is None:
        loaded = storage.query_all("account_local")
        _BUNQ_ACCOUNTS_LOCAL = []
        for acc in loaded:
            _BUNQ_ACCOUNTS_LOCAL.append(acc["value"])
        _BUNQ_ACCOUNTS_LOCAL = sorted(_BUNQ_ACCOUNTS_LOCAL,
                                      key=lambda k: k["description"])
    return _BUNQ_ACCOUNTS_LOCAL

def get_bunq_accounts_callback():
    """ Return the list of bunq accounts with a callback """
    global _BUNQ_ACCOUNTS_CALLBACK
    if _BUNQ_ACCOUNTS_CALLBACK is None:
        loaded = storage.query_all("account_callback")
        _BUNQ_ACCOUNTS_CALLBACK = []
        for acc in loaded:
            _BUNQ_ACCOUNTS_CALLBACK.append(acc["value"])
        _BUNQ_ACCOUNTS_CALLBACK = sorted(_BUNQ_ACCOUNTS_CALLBACK,
                                         key=lambda k: k["description"])
    return _BUNQ_ACCOUNTS_CALLBACK

def get_bunq_accounts_combined():
    """ Return the combined list of bunq accounts """
    accounts = []
    accounts1 = get_bunq_accounts_local()
    ibans1 = [acc["iban"] for acc in accounts1]
    accounts2 = get_bunq_accounts_callback()
    for acc1 in accounts1:
        acc = acc1.copy()
        acc["local"] = True
        for acc2 in accounts2:
            if acc["iban"] == acc2["iban"]:
                acc["enableMutation"] = acc2["enableMutation"]
                acc["enableRequest"] = acc2["enableRequest"]
                acc["callbackMutation"] = acc2["callbackMutation"]
                acc["callbackRequest"] = acc2["callbackRequest"]
                if "callbackOther"in acc2:
                    acc["callbackOther"] = acc2["callbackOther"]
        accounts.append(acc)
    for acc2 in accounts2:
        if acc2["iban"] not in ibans1:
            acc = acc2.copy()
            acc["local"] = False
            accounts.append(acc)
    return accounts

def change_account_enabled_local(iban, enabletype, value):
    """ Change the enabled status of an action on an account """
    global _BUNQ_ACCOUNTS_LOCAL
    get_bunq_accounts_local()

    if value not in ["true", "false"]:
        print("Invalid value: {}".format(value))
        return False
    value = {'true': True, 'false': False}[value]

    for acc in _BUNQ_ACCOUNTS_LOCAL:
        if acc["iban"] == iban:
            if enabletype in acc:
                acc[enabletype] = value
                return True
            print("Type not found: {}".format(enabletype))
            return False

    print("IBAN not found: {}".format(iban))
    return False

def change_account_enabled_callback(iban, enabletype, value):
    """ Change the enabled status of a callback on an account """
    global _BUNQ_ACCOUNTS_CALLBACK
    get_bunq_accounts_callback()

    if value not in ["true", "false"]:
        print("Invalid value: {}".format(value))
        return False
    value = {'true': True, 'false': False}[value]

    if get_app_mode() == 'master':
        url_base = request.url_root
    else:
        url_base = get_app_master_url()

    for acc in (x for x in _BUNQ_ACCOUNTS_CALLBACK if x["iban"] == iban):
        if enabletype == "enableMutation" and enabletype in acc:
            url_method = "bunq2ifttt_mutation"
            cat = "MUTATION"
        elif enabletype == "enableRequest" and enabletype in acc:
            url_method = "bunq2ifttt_request"
            cat = "REQUEST"
        else:
            print("Type not found: {}".format(enabletype))
            return False

        if not update_bunq_callback("{}/{}".format(acc["type"], acc["id"]),
                                    cat, value, url_base, url_method):
            return False
        update_bunq_accounts()
        return update_master_from_slave(url_base)

    print("IBAN not found: {}".format(iban))
    return False

def update_bunq_callback(accurl, cat, value, url_base, url_method):
    """ Update the bunq callback """
    res = bunq.get("v1/user/{}/{}".format(get_bunq_userid(), accurl))
    for typ in res["Response"][0]:
        data = res["Response"][0][typ]
    filtered = []
    if "notification_filters" in data:
        for filt in data["notification_filters"]:
            # keep anything not set by us
            if filt["category"] != cat or \
            not filt["notification_target"].endswith(url_method):
                filtered.append(filt)
    if value:
        filtered.append({"notification_delivery_method": "URL",
                         "notification_target": url_base + url_method,
                         "category": cat})
    print("New: ", filtered)
    res = bunq.put("v1/user/{}/{}".format(get_bunq_userid(), accurl),
                   {"notification_filters": filtered})
    if 'Error' in res:
        print("Result: ", res)
        return False
    return True

def update_master_from_slave(url_base):
    """ Update the master in case we are running in slave mode """
    if get_app_mode() == 'slave':
        data = [x.copy() for x in get_bunq_accounts_callback() \
                         if x['enableMutation'] or x['enableRequest']]
        for acc in data:
            del acc["callbackOther"]
        headers = {"Content-Type": "application/json",
                   "IFTTT-Service-Key": get_ifttt_service_key()}
        req = requests.post(url_base + "account_callback",
                            data=json.dumps(data),
                            headers=headers)
        if req.status_code != 200:
            print("Update master failed:", req.status_code, req.text)
            return False
    return True

_TYPE_TRANSLATION = {
    "MonetaryAccountBank": "monetary-account-bank",
    "MonetaryAccountJoint": "monetary-account-joint",
    "MonetaryAccountSavings": "monetary-account-savings",
}
def update_bunq_accounts():
    """ Update the list of bunq accounts for the user """
    accounts_local = []
    accounts_callback = []
    result = bunq.get("v1/user/{}/monetary-account".format(get_bunq_userid()))
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
            accounts_local.append(accinfo.copy())
            accinfo["enableMutation"] = False
            accinfo["enableRequest"] = False
            accinfo["callbackMutation"] = False
            accinfo["callbackRequest"] = False
            accinfo["callbackOther"] = []
            if "notification_filters" in acc:
                for noti in acc["notification_filters"]:
                    url = noti["notification_target"]
                    if noti["category"] == "MUTATION" and \
                    noti["notification_target"]\
                    .endswith("/bunq2ifttt_mutation"):
                        accinfo["enableMutation"] = True
                        accinfo["callbackMutation"] = url
                    elif noti["category"] == "REQUEST" and \
                    noti["notification_target"]\
                    .endswith("/bunq2ifttt_request"):
                        accinfo["enableRequest"] = True
                        accinfo["callbackRequest"] = url
                    else:
                        accinfo["callbackOther"].append(\
                            {"cat": noti["category"],
                             "url": url,
                             "b64url": base64.urlsafe_b64encode(\
                                 url.encode("utf-8")).decode("ascii")})
            accounts_callback.append(accinfo)

    process_bunq_accounts_local(accounts_local)
    if get_bunq_security_mode() == "API key":
        process_bunq_accounts_callback(accounts_callback)


def process_bunq_accounts_local(accounts):
    """ Process retrieved bunq accounts with the local dataset of accounts """
    global _BUNQ_ACCOUNTS_LOCAL
    get_bunq_accounts_local()

    default_internal = True
    default_draft = True
    for acc in _BUNQ_ACCOUNTS_LOCAL:
        # leave defaults True only if all existing accounts have True
        default_internal &= acc["enableInternal"]
        default_draft &= acc["enableDraft"]

    for acc2 in accounts:
        found = False
        for acc in _BUNQ_ACCOUNTS_LOCAL:
            if acc["iban"] == acc2["iban"]:
                # update account
                found = True
                acc["id"] = acc2["id"]
                acc["name"] = acc2["name"]
                acc["type"] = acc2["type"]
                acc["description"] = acc2["description"]
                storage.store("account_local", acc["iban"], {"value": acc})
        if not found:
            # new account
            acc2["enableInternal"] = default_internal
            acc2["enableDraft"] = default_draft
            acc2["enableExternal"] = False
            storage.store("account_local", acc2["iban"], {"value": acc2})
            _BUNQ_ACCOUNTS_LOCAL.append(acc2)

    # remove deleted
    newaccs = []
    ibans = [x["iban"] for x in accounts]
    for acc in _BUNQ_ACCOUNTS_LOCAL:
        if acc["iban"] in ibans:
            newaccs.append(acc)
        else:
            storage.remove("account_local", acc["iban"])
    _BUNQ_ACCOUNTS_LOCAL = sorted(newaccs, key=lambda k: k["description"])

def process_bunq_accounts_callback(accounts):
    """ Process bunq accounts with the callback dataset of accounts """
    global _BUNQ_ACCOUNTS_CALLBACK
    get_bunq_accounts_callback()

    for acc2 in accounts:
        found = False
        for acc in _BUNQ_ACCOUNTS_CALLBACK:
            if acc["iban"] == acc2["iban"]:
                # update account
                found = True
                acc["id"] = acc2["id"]
                acc["name"] = acc2["name"]
                acc["type"] = acc2["type"]
                acc["description"] = acc2["description"]
                acc["enableMutation"] = acc2["enableMutation"]
                acc["enableRequest"] = acc2["enableRequest"]
                acc["callbackMutation"] = acc2["callbackMutation"]
                acc["callbackRequest"] = acc2["callbackRequest"]
                if "callbackOther" in acc2:
                    acc["callbackOther"] = acc2["callbackOther"]
                else:
                    acc["callbackOther"] = []
                storage.store("account_callback", acc["iban"], {"value": acc})
        if not found:
            # new account
            storage.store("account_callback", acc2["iban"], {"value": acc2})
            _BUNQ_ACCOUNTS_CALLBACK.append(acc2)

    # remove deleted
    newaccs = []
    ibans = [x["iban"] for x in accounts]
    for acc in _BUNQ_ACCOUNTS_CALLBACK:
        if acc["iban"] in ibans:
            newaccs.append(acc)
        else:
            storage.remove("account_callback", acc["iban"])
    _BUNQ_ACCOUNTS_CALLBACK = sorted(newaccs, key=lambda k: k["description"])


def get_bunq_userid():
    """ Return the bunq userid """
    global _BUNQ_USERID
    if _BUNQ_USERID is None:
        _BUNQ_USERID = storage.retrieve("config", "bunq_userid")["value"]
    return _BUNQ_USERID

def retrieve_and_save_bunq_userid():
    """ Retrieve the bunq userid from bunq and save it """
    global _BUNQ_USERID
    result = bunq.get("v1/user")
    for user in result["Response"]:
        for typ in user:
            _BUNQ_USERID = user[typ]["id"]
    storage.store("config", "bunq_userid", {"value": _BUNQ_USERID})


def get_bunq_security_mode():
    """ Return the bunq security mode """
    global _BUNQ_SECURITY_MODE
    if _BUNQ_SECURITY_MODE is None:
        entity = storage.retrieve("config", "bunq_security_mode")
        if entity is not None:
            _BUNQ_SECURITY_MODE = entity["value"]
    return _BUNQ_SECURITY_MODE

def save_bunq_security_mode(value):
    """ Save the bunq security mode """
    global _BUNQ_SECURITY_MODE
    _BUNQ_SECURITY_MODE = value
    if value is None:
        storage.remove("config", "bunq_security_mode")
    else:
        storage.store("config", "bunq_security_mode", {"value": value})


def get_app_mode():
    """ Return the app mode (master/slave) """
    global _APP_MODE
    if _APP_MODE is None:
        entity = storage.retrieve("config", "app_mode")
        if entity is not None:
            _APP_MODE = entity["value"]
        else:
            save_app_mode('master')
    return _APP_MODE

def save_app_mode(value):
    """ Save the app mode """
    global _APP_MODE
    _APP_MODE = value
    if value is None:
        storage.remove("config", "app_mode")
    else:
        storage.store("config", "app_mode", {"value": value})


def get_app_master_url():
    """ Return the URL of the master instance """
    global _APP_MASTER_URL
    if _APP_MASTER_URL is None:
        entity = storage.retrieve("config", "app_master_url")
        if entity is not None:
            _APP_MASTER_URL = entity["value"]
    return _APP_MASTER_URL

def save_app_master_url(value):
    """ Save the URL of the master instance """
    global _APP_MASTER_URL
    _APP_MASTER_URL = value
    if value is None:
        storage.remove("config", "app_master_url")
    else:
        storage.store("config", "app_master_url", {"value": value})
