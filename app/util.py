"""
Utility methods

Mainly to handle storage and caching of some frequently used data elements
"""
# pylint: disable=global-statement

import bunq
import storage

# Use global variables as in-memory cache mechanisms
_IFTTT_SERVICE_KEY = None


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


def get_ifttt_service_key(key=None):
    """ Return the IFTTT service key, used to secure IFTTT calls """
    global _IFTTT_SERVICE_KEY
    if key not in [None, _IFTTT_SERVICE_KEY] or _IFTTT_SERVICE_KEY is None:
        entity = storage.retrieve("bunq2IFTTT", "ifttt_service_key")
        if entity is not None:
            _IFTTT_SERVICE_KEY = entity["value"]
    return _IFTTT_SERVICE_KEY

def save_ifttt_service_key(value):
    """ Save the IFTTT service key, used to secure IFTTT calls """
    global _IFTTT_SERVICE_KEY
    _IFTTT_SERVICE_KEY = value
    storage.store("bunq2IFTTT", "ifttt_service_key", {"value": value})


def check_valid_bunq_account(iban, permission=None, config=None):
    """ Return whether the account is valid for the given permission """
    accs = get_bunq_accounts(permission, config)
    for acc in accs:
        if acc["iban"] == iban:
            return True, acc["description"]
    return False, ""

def get_bunq_accounts(permission=None, config=None):
    """ Return the list of accounts for the given permission """
    if config is None:
        config = bunq.retrieve_config()
    result = []
    for acc in config["accounts"]:
        if permission is None or (acc["iban"] in config["permissions"] and \
                           permission in config["permissions"][acc["iban"]] \
                           and config["permissions"][acc["iban"]][permission]):
            result.append(acc)
    return result

def get_bunq_accounts_with_permissions(config):
    """ Return the list of accounts with permissions """
    results = []
    perms = {}
    if "permissions" in config:
        perms = config["permissions"]
    if "accounts" in config:
        for acc in config["accounts"]:
            acc2 = acc.copy()
            acc2["perms"] = {}
            if acc["iban"] in perms:
                for enable in perms[acc["iban"]]:
                    acc2["perms"][enable] = perms[acc["iban"]][enable]
            results.append(acc2)
    return results

def update_bunq_accounts():
    """ Update the list of bunq accounts """
    config = bunq.retrieve_config()
    bunq.retrieve_accounts(config)
    sync_permissions(config)
    bunq.save_config(config)

def sync_permissions(config):
    """ Synchronize permissions between the old and new account lists """
    perms = config["permissions"] if "permissions" in config else {}
    accs = config["accounts"]

    # The default depends on the current setting:
    # - if some have permissions for accounts have been explicitly disabled,
    #   the default is to disable these for new accounts as well
    # - if not, all permissions are by default enabled - except external
    #   payments which are always disabled by default
    defaults = {
        "Internal": True,
        "Draft": True,
        "External": False,
        "Mutation": True,
        "Request": True,
        "Card": True,
        "PaymentRequest": True,
    }
    for iban in perms:
        for perm in perms[iban]:
            if not perms[iban][perm]:
                defaults[perm] = False

    # Set default permissions for new accounts / new permissions
    ibans = []
    for acc in accs:
        iban = acc["iban"]
        ibans.append(iban)
        if iban not in perms:
            perms[iban] = defaults.copy()
        else:
            for perm in defaults:
                if perm not in perms[iban]:
                    perms[iban][perm] = defaults[perm]

    # Remove any old accounts
    newperms = {}
    for iban in perms:
        if iban in ibans:
            newperms[iban] = perms[iban]
    config["permissions"] = newperms

def account_change_permission(iban, permission, value):
    """ Change a permission on an account """
    if permission not in ["Internal", "Draft", "Mutation", "Request", "Card"] \
    and not (permission == "External" and get_external_payment_enabled()):
        print("Invalid permission: "+permission)
        return False

    if value not in ["true", "false"]:
        print("Invalid value: "+value)
        return False
    value = (value == "true")

    config = bunq.retrieve_config()
    if "permissions" not in config:
        config["permissions"] = {}

    if iban not in config["permissions"]:
        config["permissions"][iban] = {}

    config["permissions"][iban][permission] = value
    bunq.save_config(config)
    return True
