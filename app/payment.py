"""
Payments

Handles the draft, internal & external payment actions
"""

import json
import uuid

from flask import request

import bunq
import util


def create_payment_message(internal, fields, config):
    """ Get the payment message """

    # check for required fields
    expected_fields = ["amount", "source_account", "target_account",
                       "description"]
    if not internal:
        expected_fields.append("target_name")
    for field in expected_fields:
        if field not in fields:
            errmsg = "missing field: "+field
            print("[action_payment] ERROR: "+errmsg)
            return {"errors": [{"status": "SKIP", "message": errmsg}]}

    # strip spaces from account numbers
    fields["source_account"] = fields["source_account"].replace(" ", "")
    fields["target_account"] = fields["target_account"].replace(" ", "")

    # check amount
    try:
        amount = float(fields["amount"])
    except ValueError:
        amount = -1
    if amount <= 0:
        errmsg = "only positive amounts allowed: "+fields["amount"]
        print("[action_payment] ERROR: "+errmsg)
        return {"errors": [{"status": "SKIP", "message": errmsg}]}

    # the account NL42BUNQ0123456789 is used for test payments
    if fields["source_account"] == "NL42BUNQ0123456789":
        return {"data": [{"id": uuid.uuid4().hex}]}

    # for internal payments we need to find the target account name
    if internal:
        target_name = None
        for acc in config["accounts"]:
            if acc["iban"] == fields["target_account"]:
                target_name = acc["name"]
        if target_name is None:
            errmsg = "unknown target account: "+fields["target_account"]
            print("[action_payment] ERROR: "+errmsg)
            return {"errors": [{"status": "SKIP", "message": errmsg}]}
    else:
        target_name = fields["target_name"]

    # create the payment message
    payment = {
        "amount": {
            "value": "{:.2f}".format(amount),
            "currency": "EUR"
        },
        "counterparty_alias": {
            "type": "IBAN",
            "value": fields["target_account"],
            "name": target_name
        },
        "description": fields["description"]
    }
    print(payment)
    return payment


def check_source_account(internal, draft, config, iban):
    """ Find the source account id and check if payment is allowed """
    for acc in config["accounts"]:
        if acc["iban"] == iban:
            source_accid = acc["id"]

    result = False
    if "permissions" in config:
        if iban in config["permissions"]:
            if internal and "Internal" in config["permissions"][iban]:
                result = config["permissions"][iban]["Internal"]
            elif draft and "Draft" in config["permissions"][iban]:
                result = config["permissions"][iban]["Draft"]
            elif "External" in config["permissions"][iban]:
                result = config["permissions"][iban]["External"]

    return source_accid, result


def ifttt_bunq_payment(internal, draft):
    """ Execute a draft, internal or external payment """
    config = bunq.retrieve_config()
    data = request.get_json()
    print("[action_payment] input: {}".format(json.dumps(data)))

    errmsg = None
    if not internal and not draft and not util.get_external_payment_enabled():
        errmsg = "external payments disabled"
    if "actionFields" not in data:
        errmsg = "missing actionFields"

    if errmsg:
        print("[action_payment] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    # get the payment message
    fields = data["actionFields"]
    msg = create_payment_message(internal, fields, config)
    if "errors" in msg or "data" in msg: # error or test payment
        return json.dumps(msg), 400 if "errors" in msg else 200

    # find the source account id
    source_accid, enabled = check_source_account(internal, draft, config,
                                                 fields["source_account"])
    if source_accid is None:
        errmsg = "unknown source account: "+fields["source_account"]
    if not enabled:
        errmsg = "Payment type not enabled for account: "+\
                 fields["source_account"]

    if errmsg:
        print("[action_payment] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    # execute the payment
    if draft:
        msg = {"number_of_required_accepts": 1, "entries": [msg]}
        result = bunq.post("v1/user/{}/monetary-account/{}/draft-payment"
                           .format(config["user_id"], source_accid), msg)
    else:
        result = bunq.post("v1/user/{}/monetary-account/{}/payment"
                           .format(config["user_id"], source_accid), msg)
    print(result)
    if "Error" in result:
        return json.dumps({"errors": [{
            "status": "SKIP",
            "message": result["Error"][0]["error_description"]
        }]}), 400

    return json.dumps({"data": [{
        "id": str(result["Response"][0]["Id"]["id"])}]})
