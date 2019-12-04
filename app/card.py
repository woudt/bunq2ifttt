"""
Card

Handles the card change account action
"""

import json
import uuid

from flask import request

import util
import bunq


def get_bunq_cards():
    """ Return the list of bunq cards """
    config = bunq.retrieve_config()
    data = bunq.get("v1/user/{}/card".format(config["user_id"]), config)
    results = []
    for item in data["Response"]:
        for typ in item:
            card = item[typ]
            if card["status"] == "ACTIVE":
                if card["type"] != "MASTERCARD_VIRTUAL":
                    print(card)
                    results.append({
                        "label": card["second_line"],
                        "value": str(card["id"])
                    })
    return sorted(results, key=lambda k: k["label"])


def change_card_account():
    """ Execute a change card account action """
    data = request.get_json()
    print("[change_card_account] input: {}".format(json.dumps(data)))

    errmsg = None
    if "actionFields" not in data:
        errmsg = "missing actionFields"
    else:
        fields = data["actionFields"]
        expected_fields = ["account", "card"]
        for field in expected_fields:
            if field not in fields:
                errmsg = "missing field: "+field

    if errmsg:
        print("[change_card_account] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    fields["account"] = fields["account"].replace(" ", "")

    # the account NL42BUNQ0123456789 is used for test payments
    if fields["account"] == "NL42BUNQ0123456789":
        return json.dumps({"data": [{"id": uuid.uuid4().hex}]})

    accountid = None
    for acc in util.get_bunq_accounts("Card"):
        if acc["iban"] == fields["account"]:
            accountid = acc["id"]
    if accountid is None:
        errmsg = "unknown account: "+fields["account"]
        print("[change_card_account] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    if "pin_ordinal" in fields:
        pinord = fields["pin_ordinal"]
    else:
        pinord = "PRIMARY"

    msg = {"pin_code_assignment": [{
        "type": pinord,
        "monetary_account_id": int(accountid),
    }]}

    config = bunq.retrieve_config()
    data = bunq.get("v1/user/{}/card".format(config["user_id"]), config)
    for item in data["Response"]:
        for typ in item:
            card = item[typ]
            if str(card["id"]) == str(fields["card"]):
                for pca in card["pin_code_assignment"]:
                    if pca["type"] != pinord:
                        msg["pin_code_assignment"].append({
                            "type": pca["type"],
                            "monetary_account_id": pca["monetary_account_id"]
                        })

    res = bunq.session_request_encrypted("PUT", "v1/user/{}/card/{}".format(
        config["user_id"], fields["card"]), msg, config)
    if "Error" in res:
        print(json.dumps(res))
        errmsg = "Bunq API call failed, see the logs!"
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    return json.dumps({"data": [{"id": uuid.uuid4().hex}]})
