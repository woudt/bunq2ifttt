"""
Inquiry

Handles the request inquiry (payment request) action
"""

import json
import uuid

from flask import request

import util
import bunq


def request_inquiry():
    """ Execute a request inquiry action """
    data = request.get_json()
    print("[request_inquiry] input: {}".format(json.dumps(data)))

    errmsg = None
    if "actionFields" not in data:
        errmsg = "missing actionFields"
    else:
        fields = data["actionFields"]
        expected_fields = ["amount", "account", "phone_email_iban"]
        for field in expected_fields:
            if field not in fields:
                errmsg = "missing field: "+field

    if errmsg:
        print("[request_inquiry] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    fields["account"] = fields["account"].replace(" ", "")

    # the account NL42BUNQ0123456789 is used for test payments
    if fields["account"] == "NL42BUNQ0123456789":
        return json.dumps({"data": [{"id": uuid.uuid4().hex}]})

    accountid = None
    for acc in util.get_bunq_accounts("PaymentRequest"):
        if acc["iban"] == fields["account"]:
            accountid = acc["id"]
    if accountid is None:
        errmsg = "unknown account: "+fields["account"]
        print("[request_inquiry] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    # check amount
    try:
        amount = float(fields["amount"])
    except ValueError:
        amount = -1
    if amount <= 0:
        errmsg = "only positive amounts allowed: "+fields["amount"]
        print("[action_payment] ERROR: "+errmsg)
        return {"errors": [{"status": "SKIP", "message": errmsg}]}

    # check phone or email
    bmvalue = fields["phone_email_iban"].replace(" ", "")
    if "@" in bmvalue:
        bmtype = "EMAIL"
    elif bmvalue[:1] == "+" and bmvalue[1:].isdecimal():
        bmtype = "PHONE_NUMBER"
    elif bmvalue[:2].isalpha() and bmvalue[2:4].isdecimal():
        bmtype = "IBAN"
    else:
        errmsg = "Unrecognized as email, phone or iban: "+bmvalue
        print("[request_inquiry] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    description = fields["description"] if "description" in fields else ""
    msg = {
        "amount_inquired": {
            "value": "{:.2f}".format(amount),
            "currency": "EUR",
        },
        "counterparty_alias": {
            "type": bmtype,
            "name": bmvalue,
            "value": bmvalue
        },
        "description": description,
        "allow_bunqme": True,
    }
    print(json.dumps(msg))

    config = bunq.retrieve_config()
    data = bunq.post("v1/user/{}/monetary-account/{}/request-inquiry".format(\
                     config["user_id"], accountid), msg, config)
    print(data)
    if "Error" in data:
        return json.dumps({"errors": [{
            "status": "SKIP",
            "message": data["Error"][0]["error_description"]
        }]}), 400

    return json.dumps({"data": [{"id": uuid.uuid4().hex}]})
