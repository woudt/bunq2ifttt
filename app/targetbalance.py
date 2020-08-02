"""
Target balance

Handles the target balance internal/external actions
"""

import json
import uuid

from flask import request

import bunq
import payment


def target_balance_internal():
    """ Execute a target balance internal action """
    data = request.get_json()
    print("[target_balance_internal] input: {}".format(json.dumps(data)))

    if "actionFields" not in data:
        errmsg = "missing actionFields"
        print("[target_balance_internal] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    fields = data["actionFields"]
    errmsg = check_fields(True, fields)
    if errmsg:
        print("[target_balance_internal] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    # the account NL42BUNQ0123456789 is used for test payments
    if fields["account"] == "NL42BUNQ0123456789":
        return json.dumps({"data": [{"id": uuid.uuid4().hex}]})

    # retrieve balance
    config = bunq.retrieve_config()
    if fields["payment_type"] == "DIRECT":
        balance = get_balance(config, fields["account"],
                              fields["other_account"])
        if isinstance(balance, tuple):
            balance, balance2 = balance
            transfer_amount = fields["amount"] - balance
            if transfer_amount > balance2:
                transfer_amount = balance2
    else:
        balance = get_balance(config, fields["account"])
        if isinstance(balance, float):
            transfer_amount = fields["amount"] - balance

    if isinstance(balance, str):
        errmsg = balance
        print("[target_balance_internal] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    # construct payment message
    if "{:.2f}".format(fields["amount"]) == "0.00":
        errmsg = "No transfer needed, balance already ok"
        print("[target_balance_internal] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    if transfer_amount > 0 and "top up" in fields["direction"]:
        paymentmsg = {
            "amount": {
                "value": "{:.2f}".format(transfer_amount),
                "currency": "EUR"
            },
            "counterparty_alias": {
                "type": "IBAN",
                "value": fields["account"],
                "name": "x"
            },
            "description": fields["description"]
        }
        account = fields["other_account"]
    elif transfer_amount < 0 and "skim" in fields["direction"]:
        paymentmsg = {
            "amount": {
                "value": "{:.2f}".format(-transfer_amount),
                "currency": "EUR"
            },
            "counterparty_alias": {
                "type": "IBAN",
                "value": fields["other_account"],
                "name": "x"
            },
            "description": fields["description"]
        }
        account = fields["account"]
    else:
        errmsg = "No transfer needed, balance already ok"
        print("[target_balance_internal] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    print(paymentmsg)

    # get id and check permissions
    if fields["payment_type"] == "DIRECT":
        accid, enabled = payment.check_source_account(True, False, config,
                                                      account)
    else:
        accid, enabled = payment.check_source_account(False, True, config,
                                                      account)
    if accid is None:
        errmsg = "unknown account: "+account
    if not enabled:
        errmsg = "Payment type not enabled for account: "+account

    if errmsg:
        print("[target_balance_internal] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    # execute the payment
    if fields["payment_type"] == "DIRECT":
        result = bunq.post("v1/user/{}/monetary-account/{}/payment"
                           .format(config["user_id"], accid), paymentmsg)
    else:
        paymentmsg = {"number_of_required_accepts": 1, "entries": [paymentmsg]}
        result = bunq.post("v1/user/{}/monetary-account/{}/draft-payment"
                           .format(config["user_id"], accid), paymentmsg)
    print(result)
    if "Error" in result:
        return json.dumps({"errors": [{
            "status": "SKIP",
            "message": result["Error"][0]["error_description"]
        }]}), 400

    return json.dumps({"data": [{
        "id": str(result["Response"][0]["Id"]["id"])}]})


def target_balance_external():
    """ Execute a target balance external action """
    data = request.get_json()
    print("[target_balance_external] input: {}".format(json.dumps(data)))

    if "actionFields" not in data:
        errmsg = "missing actionFields"
        print("[target_balance_external] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    fields = data["actionFields"]
    errmsg = check_fields(False, fields)
    if errmsg:
        print("[target_balance_external] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    # the account NL42BUNQ0123456789 is used for test payments
    if fields["account"] == "NL42BUNQ0123456789":
        return json.dumps({"data": [{"id": uuid.uuid4().hex}]})

    # retrieve balance
    config = bunq.retrieve_config()
    balance = get_balance(config, fields["account"])
    if isinstance(balance, str):
        errmsg = balance
        print("[target_balance_external] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    transfer_amount = fields["amount"] - balance

    # check for zero transfer
    if "{:.2f}".format(fields["amount"]) == "0.00":
        errmsg = "No transfer needed, balance already ok"
        print("[target_balance_external] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    # get account id and check permission
    if transfer_amount > 0:
        accid = None
        for acc in config["accounts"]:
            if acc["iban"] == fields["account"]:
                accid = acc["id"]

        enabled = False
        if "permissions" in config:
            if fields["account"] in config["permissions"]:
                if "PaymentRequest" in config["permissions"]\
                                             [fields["account"]]:
                    enabled = config["permissions"][fields["account"]]\
                                    ["PaymentRequest"]
    else:
        accid, enabled = payment.check_source_account(False, True, config,
                                                      fields["account"])

    if accid is None:
        errmsg = "unknown account: "+fields["account"]
    if not enabled:
        errmsg = "Not permitted for account: "+fields["account"]

    if errmsg:
        print("[target_balance_external] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
               , 400

    # send request / execute payment
    if transfer_amount > 0 and "top up" in fields["direction"]:

        bmvalue = fields["request_phone_email_iban"].replace(" ", "")
        if "@" in bmvalue:
            bmtype = "EMAIL"
        elif bmvalue[:1] == "+" and bmvalue[1:].isdecimal():
            bmtype = "PHONE_NUMBER"
        elif bmvalue[:2].isalpha() and bmvalue[2:4].isdecimal():
            bmtype = "IBAN"
        else:
            errmsg = "Unrecognized as email, phone or iban: "+bmvalue
            print("[request_inquiry] ERROR: "+errmsg)
            return json.dumps({"errors": [{"status": "SKIP", "message":\
                   errmsg}]}), 400

        msg = {
            "amount_inquired": {
                "value": "{:.2f}".format(transfer_amount),
                "currency": "EUR",
            },
            "counterparty_alias": {
                "type": bmtype,
                "name": bmvalue,
                "value": bmvalue
            },
            "description": fields["request_description"],
            "allow_bunqme": True,
        }
        print(json.dumps(msg))

        config = bunq.retrieve_config()
        result = bunq.post("v1/user/{}/monetary-account/{}/request-inquiry"\
                           .format(config["user_id"], accid), msg, config)

    elif transfer_amount < 0 and "skim" in fields["direction"]:
        paymentmsg = {
            "amount": {
                "value": "{:.2f}".format(-transfer_amount),
                "currency": "EUR"
            },
            "counterparty_alias": {
                "type": "IBAN",
                "value": fields["payment_account"],
                "name": fields["payment_name"]
            },
            "description": fields["payment_description"]
        }
        print(paymentmsg)
        paymentmsg = {"number_of_required_accepts": 1, "entries": [paymentmsg]}
        result = bunq.post("v1/user/{}/monetary-account/{}/draft-payment"
                           .format(config["user_id"], accid), paymentmsg)

    else:
        errmsg = "No transfer needed, balance already ok"
        print("[target_balance_external] ERROR: "+errmsg)
        return json.dumps({"errors": [{"status": "SKIP", "message": errmsg}]})\
                , 400

    print(result)
    if "Error" in result:
        return json.dumps({"errors": [{
            "status": "SKIP",
            "message": result["Error"][0]["error_description"]
        }]}), 400

    return json.dumps({"data": [{
        "id": str(result["Response"][0]["Id"]["id"])}]})


def check_fields(internal, fields):
    """ Check the fields """
    # check expected fields
    if internal:
        expected_fields = ["account", "amount", "other_account", "direction",
                           "payment_type", "description"]
    else:
        expected_fields = ["account", "amount", "direction", "payment_account",
                           "payment_name", "payment_description",
                           "request_phone_email_iban", "request_description"]

    for field in expected_fields:
        if field not in fields:
            return "missing field: "+field

    # strip spaces from account numbers
    fields["account"] = fields["account"].replace(" ", "")
    if internal:
        fields["other_account"] = fields["other_account"].replace(" ", "")
    else:
        fields["payment_account"] = fields["payment_account"].replace(" ", "")

    # check amount
    try:
        orig = fields["amount"]
        fields["amount"] = float(fields["amount"])
    except ValueError:
        fields["amount"] = -1
    if fields["amount"] <= 0:
        return "only positive amounts allowed: "+orig

    return None


def get_balance(config, account, account2=None):
    """ Retrieve the balance of one or two accounts """
    balances = bunq.retrieve_account_balances(config)
    if account2 is None and account in balances:
        return balances[account]
    if account in balances and account2 in balances:
        return balances[account], balances[account2]
    if account not in balances:
        return "Account balance not found "+account
    return "Account balance not found "+account2
