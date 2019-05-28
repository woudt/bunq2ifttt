"""
Events

Handles all events:
- callbacks from bunq
- ifttt triggers on the events received from bunq
"""
# pylint: disable=broad-except

import json
import traceback
import uuid

import arrow
import requests

from flask import request

import storage
import util


###############################################################################
# Callback methods called by bunq
###############################################################################

def bunq_callback_request():
    """ Handle bunq callbacks of type REQUEST """
    try:
        data = request.get_json()
        print("[bunqcb_request] input: {}".format(json.dumps(data)))
        if data["NotificationUrl"]["event_type"] != "REQUEST_RESPONSE_CREATED":
            print("[bunqcb_request] ignoring {} event"
                  .format(data["NotificationUrl"]["event_type"]))
            return ""

        obj = data["NotificationUrl"]["object"]["RequestResponse"]
        metaid = obj["id"]
        if storage.seen("seen_request", metaid):
            print("[bunqcb_request] duplicate transaction")
            return ""

        iban = obj["alias"]["iban"]
        item = {
            "created_at": obj["created"],
            "date": arrow.get(obj["created"]).format("YYYY-MM-DD"),
            "amount": obj["amount_inquired"]["value"],
            "account": iban,
            "counterparty_account": counterparty_account(obj),
            "counterparty_name": obj["counterparty_alias"]["display_name"],
            "description": obj["description"],
            "request_id": metaid,
            "meta": {
                "id": metaid,
                "timestamp": arrow.get(obj["created"]).timestamp
            }
        }

        print("[bunqcb_request] translated: {}".format(json.dumps(item)))

        triggerids = []
        for account in ["ANY", iban]:
            for trigger in storage.query("trigger_request",
                                         "account", "=", account):
                if check_fields(item, trigger["fields"]):
                    ident = trigger["identity"]
                    triggerids.append(ident)
                    storage.store("request_"+ident, metaid, {"value": item})
        print("[bunqcb_request] Matched triggers:", json.dumps(triggerids))
        if triggerids:
            data = {"data": []}
            for triggerid in triggerids:
                data["data"].append({"trigger_identity": triggerid})
            headers = {
                "IFTTT-Channel-Key": util.get_ifttt_service_key(),
                "IFTTT-Service-Key": util.get_ifttt_service_key(),
                "X-Request-ID": uuid.uuid4().hex,
                "Content-Type": "application/json"
            }
            print("[bunqcb_request] to ifttt: {}".format(json.dumps(data)))
            res = requests.post("https://realtime.ifttt.com/v1/notifications",
                                headers=headers, data=json.dumps(data))
            print("[bunqcb_request] result: {} {}"
                  .format(res.status_code, res.text))

    except Exception:
        traceback.print_exc()
        print("[bunqcb_request] ERROR during handling bunq callback")
    return ""

def bunq_callback_mutation():
    """ Handle bunq callbacks of type MUTATION """
    try:
        data = request.get_json()
        print("[bunqcb_mutation] input: {}".format(json.dumps(data)))
        payment = data["NotificationUrl"]["object"]["Payment"]
        metaid = payment["id"]
        if storage.seen("seen_mutation", metaid):
            print("[bunqcb_mutation] duplicate transaction")
            return ""

        iban = payment["alias"]["iban"]
        item = {
            "created_at": payment["created"],
            "date": arrow.get(payment["created"]).format("YYYY-MM-DD"),
            "type": mutation_type(payment),
            "amount": payment["amount"]["value"],
            "balance": payment["balance_after_mutation"]["value"],
            "account": iban,
            "counterparty_account": counterparty_account(payment),
            "counterparty_name": payment["counterparty_alias"]["display_name"],
            "description": payment["description"],
            "payment_id": metaid,
            "meta": {
                "id": metaid,
                "timestamp": arrow.get(payment["created"]).timestamp
            }
        }

        print("[bunqcb_mutation] translated: {}".format(json.dumps(item)))
        triggerids_1 = []
        triggerids_2 = []
        for account in ["ANY", iban]:
            for trigger in storage.query("trigger_mutation",
                                         "account", "=", account):
                if check_fields(item, trigger["fields"]):
                    ident = trigger["identity"]
                    triggerids_1.append(ident)
                    storage.store("mutation_"+ident, metaid, {"value": item})
            for trigger in storage.query("trigger_balance",
                                         "account", "=", account):
                if check_fields(item, trigger["fields"]):
                    ident = trigger["identity"]
                    triggerids_2.append(ident)
                    storage.store("balance_"+ident, metaid, {"value": item})
        print("Matched mutation triggers:", json.dumps(triggerids_1))
        print("Matched balance triggers:", json.dumps(triggerids_2))
        data = {"data": []}
        for triggerids in [triggerids_1, triggerids_2]:
            for triggerid in triggerids:
                data["data"].append({"trigger_identity": triggerid})
        if data["data"]:
            headers = {
                "IFTTT-Channel-Key": util.get_ifttt_service_key(),
                "IFTTT-Service-Key": util.get_ifttt_service_key(),
                "X-Request-ID": uuid.uuid4().hex,
                "Content-Type": "application/json"
            }
            print("[bunqcb_mutation] to ifttt: {}".format(
                json.dumps(data)))
            res = requests.post("https://realtime.ifttt.com/v1/notifications",
                                headers=headers, data=json.dumps(data))
            print("[bunqcb_mutation] result: {} {}"
                  .format(res.status_code, res.text))

    except Exception:
        traceback.print_exc()
        print("[bunqcb_mutation] ERROR during handling bunq callback")

    return ""


###############################################################################
# Helper methods for bunq callbacks
###############################################################################

def mutation_type(payment):
    """ Return the type of a payment """
    muttype = "TRANSFER_OTHER"
    if payment["type"] == "MASTERCARD":
        muttype = "CARD_" + payment["sub_type"]
    elif payment["type"] == "IDEAL" or payment["type"] == "BUNQME":
        # if a bunq account is used to pay a bunq.me request, type=BUNQME
        # if another dutch bank is used, type=IDEAL
        # but there really is no difference, so we
        muttype = "ONLINE_IDEAL"
    elif payment["type"] == "SOFORT":
        muttype = "ONLINE_SOFORT"
    elif payment["type"] == "EBA_SCT":
        muttype = "TRANSFER_REGULAR"
    elif payment["type"] == "SAVINGS":
        muttype = "TRANSFER_SAVINGS"
    elif payment["type"] == "INTEREST":
        muttype = "BUNQ_INTEREST"
    elif payment["type"] == "BUNQ":
        if payment["sub_type"] in ["BILLING", "REWARD"]:
            muttype = "BUNQ_"+payment["sub_type"]
        elif payment["sub_type"] == "REQUEST":
            muttype = "TRANSFER_REQUEST"
        elif payment["sub_type"] == "PAYMENT":
            if "scheduled_id" in payment \
            and payment["scheduled_id"] is not None:
                muttype = "TRANSFER_SCHEDULED"
            else:
                muttype = "TRANSFER_REGULAR"
    return muttype

def counterparty_account(payment):
    """ Return the counterparty account, potentially using default values in
        case no account is available """
    if "counterparty_alias" in payment \
    and "iban" in payment["counterparty_alias"]:
        ctp_account = payment["counterparty_alias"]["iban"]
    elif payment["type"] == "MASTERCARD":
        ctp_account = "Card"
    elif payment["type"] == "IDEAL":
        ctp_account = "iDEAL"
    elif payment["type"] == "SOFORT":
        ctp_account = "SOFORT"
    else:
        ctp_account = "Other"
    return ctp_account

def check_fields(item, fields):
    """ Check the conditional fields for a trigger """
    return check_types(item, fields) and check_comparators(item, fields)

def check_types(item, fields):
    """ Check the mutation type fields for a trigger """
    result = True
    if "type" in fields and fields["type"] != "ANY":
        result &= item["type"].startswith(fields["type"])
    if "type_2" in fields and fields["type_2"] != "---":
        result &= item["type"].startswith(fields["type_2"])
    if "type_3" in fields and fields["type_3"] != "---":
        result &= item["type"].startswith(fields["type_3"])
    if "type_4" in fields and fields["type_4"] != "---":
        result &= item["type"].startswith(fields["type_4"])
    return result

def check_comparators(item, fields):
    """ Check the comparison fields for a trigger """
    result = True
    if "amount_comparator" in fields and fields["amount_value"] != "":
        result &= check_field_num(item["amount"],
                                  fields["amount_comparator"],
                                  fields["amount_value"])
    if "amount_comparator_2" in fields and fields["amount_value_2"] != "":
        result &= check_field_num(item["amount"],
                                  fields["amount_comparator_2"],
                                  fields["amount_value_2"])
    if "balance_comparator" in fields and fields["balance_value"] != "":
        result &= check_field_num(item["balance"],
                                  fields["balance_comparator"],
                                  fields["balance_value"])
    if "balance_comparator_2" in fields and fields["balance_value_2"] != "":
        result &= check_field_num(item["balance"],
                                  fields["balance_comparator_2"],
                                  fields["balance_value_2"])
    if "counterparty_name_comparator" in fields \
    and fields["counterparty_name_value"] != "":
        result &= check_field_str(item["counterparty_name"],
                                  fields["counterparty_name_comparator"],
                                  fields["counterparty_name_value"])
    if "counterparty_name_comparator_2" in fields \
    and fields["counterparty_name_value_2"] != "":
        result &= check_field_str(item["counterparty_name"],
                                  fields["counterparty_name_comparator_2"],
                                  fields["counterparty_name_value_2"])
    if "counterparty_account_comparator" in fields \
    and fields["counterparty_account_value"] != "":
        result &= check_field_str(item["counterparty_account"],
                                  fields["counterparty_account_comparator"],
                                  fields["counterparty_account_value"])
    if "counterparty_account_comparator_2" in fields \
    and fields["counterparty_account_value_2"] != "":
        result &= check_field_str(item["counterparty_account"],
                                  fields["counterparty_account_comparator"],
                                  fields["counterparty_account_value_2"])
    if "description_comparator" in fields \
    and fields["description_value"] != "":
        result &= check_field_str(item["description"],
                                  fields["description_comparator"],
                                  fields["description_value"])
    if "description_comparator_2" in fields \
    and fields["description_value_2"] != "":
        result &= check_field_str(item["description"],
                                  fields["description_comparator_2"],
                                  fields["description_value_2"])
    return result

def check_field_num(orig, comparator, target):
    """ Check a numeric field """
    result = False
    if comparator == "equal" and float(orig) == float(target):
        result = True
    elif comparator == "not_equal" and float(orig) != float(target):
        result = True
    elif comparator == "above" and float(orig) > float(target):
        result = True
    elif comparator == "above_equal" and float(orig) >= float(target):
        result = True
    elif comparator == "below" and float(orig) < float(target):
        result = True
    elif comparator == "below_equal" and float(orig) <= float(target):
        result = True
    elif comparator == "in" and orig in json.loads(target):
        result = True
    elif comparator == "not_in" and orig not in json.loads(target):
        result = True
    return result

def check_field_str(orig, comparator, target):
    """ Check a string field """
    result = False
    if comparator in ["equal_nc", "not_equal_nc", "cont_nc", "not_cont_nc",
                      "in_nc", "not_in_nc"]:
        orig = orig.casefold()
        target = target.casefold()
    if comparator in ["equal", "equal_nc"] and orig == target:
        result = True
    elif comparator in ["not_equal", "not_equal_nc"] and orig != target:
        result = True
    elif comparator in ["cont", "cont_nc"] and orig.find(target) > -1:
        result = True
    elif comparator in ["not_cont", "not_cont_nc"] and orig.find(target) == -1:
        result = True
    elif comparator in ["in", "in_nc"] and orig in json.loads(target):
        result = True
    elif comparator in ["not_in", "in_nc"] and orig not in json.loads(target):
        result = True
    return result


###############################################################################
# IFTTT trigger bunq_mutation
###############################################################################

def trigger_mutation():
    """ Callback for IFTTT trigger bunq_mutation """
    try:
        data = request.get_json()
        print("[trigger_mutation] input: {}".format(json.dumps(data)))

        if "triggerFields" not in data or\
                "account" not in data["triggerFields"]:
            print("[trigger_mutation] ERROR: account field missing!")
            return json.dumps({"errors": [{"message": "Invalid data"}]}), 400
        account = data["triggerFields"]["account"]
        fields = data["triggerFields"]
        fieldsstr = json.dumps(fields)

        if "trigger_identity" not in data:
            print("[trigger_mutation] ERROR: trigger_identity field missing!")
            return json.dumps({"errors": [{"message": "Invalid data"}]}), 400
        identity = data["trigger_identity"]

        limit = 50
        if "limit" in data:
            limit = data["limit"]

        if account == "NL42BUNQ0123456789":
            return trigger_mutation_test(limit)

        timezone = "UTC"
        if "user" in data and "timezone" in data["user"]:
            timezone = data["user"]["timezone"]

        entity = storage.retrieve("trigger_mutation", identity)
        if entity is not None:
            if entity["account"] != account or \
                    json.dumps(entity["fields"]) != fieldsstr:
                storage.store("trigger_mutation", identity, {
                    "account": account,
                    "identity": identity,
                    "fields": fields
                })
                print("[trigger_mutation] updating trigger {} {}"
                      .format(account, fieldsstr))
        else:
            storage.store("trigger_mutation", identity, {
                "account": account,
                "identity": identity,
                "fields": fields
            })
            storage.store("mutation_"+identity, "0", {"value": {
                "created_at": "2018-01-05T11:25:15+00:00",
                "date": "2018-01-05",
                "type": "MANUAL",
                "amount": "0.00",
                "balance": "0.00",
                "account": account,
                "counterparty_account": "NL11BANK1111111111",
                "counterparty_name": "Dummy Transaction",
                "description": "This is a dummy transaction",
                "payment_id": "123e4567-e89b-12d3-a456-426655440001",
                "meta": {
                    "id": "0",
                    "timestamp": "1515151515"
                }
            }})
            print("[trigger_mutation] storing new trigger {} {}"
                  .format(account, fieldsstr))

        transactions = []
        for entity in storage.query_all("mutation_" + identity):
            entity["value"]["created_at"] = arrow.get(\
                entity["value"]["created_at"]).to(timezone).isoformat()
            transactions.append(entity["value"])
        transactions = sorted(transactions,
                              key=lambda k: -int(k["meta"]["timestamp"]))

        if len(transactions) > 50:
            for trans in transactions[50:]:
                storage.remove("mutation_"+identity, str(trans["meta"]["id"]))

        print("[trigger_mutation] Found {} transactions"
              .format(len(transactions)))
        return json.dumps({"data": transactions[:limit]})
    except Exception:
        traceback.print_exc()
        print("[trigger_mutation] ERROR: cannot retrieve transactions")
        return json.dumps({"errors": [{"message": \
                           "Cannot retrieve transactions"}]}), 400


def trigger_mutation_test(limit):
    """ Test data for IFTTT trigger bunq_mutation """
    result = [{
        "created_at": "2018-01-05T11:25:15+00:00",
        "date": "2018-01-05",
        "type": "MANUAL",
        "amount": "1.01",
        "balance": "15.15",
        "account": "NL42BUNQ0123456789",
        "counterparty_account": "NL11BANK1111111111",
        "counterparty_name": "John Doe",
        "description": "Here you are",
        "payment_id": "123e4567-e89b-12d3-a456-426655440001",
        "meta": {
            "id": "1",
            "timestamp": "1515151515"
        }
    }, {
        "created_at": "2014-10-24T09:03:34+00:00",
        "date": "2014-10-24",
        "type": "MANUAL",
        "amount": "2.02",
        "balance": "14.14",
        "account": "NL42BUNQ0123456789",
        "counterparty_account": "NL22BANK2222222222",
        "counterparty_name": "Jane Doe",
        "description": "What I owe you",
        "payment_id": "123e4567-e89b-12d3-a456-426655440002",
        "meta": {
            "id": "2",
            "timestamp": "1414141414"
        }
    }, {
        "created_at": "2008-05-30T04:20:12+00:00",
        "date": "2008-05-30",
        "type": "MANUAL",
        "amount": "-3.03",
        "balance": "12.12",
        "account": "NL42BUNQ0123456789",
        "counterparty_account": "",
        "counterparty_name": "ACME Store Inc.",
        "description": "POS transaction 1234567890",
        "payment_id": "123e4567-e89b-12d3-a456-426655440003",
        "meta": {
            "id": "3",
            "timestamp": "1212121212"
        }
    }]
    return json.dumps({"data": result[:limit]})


def trigger_mutation_delete(identity):
    """ Delete a specific trigger identity for IFTTT trigger bunq_mutation """
    try:
        for index in storage.query_indexes("mutation_"+identity):
            storage.remove("mutation_"+identity, index)
        storage.remove("trigger_mutation", identity)

        return ""
    except Exception:
        traceback.print_exc()
        print("[trigger_mutation_delete] ERROR: cannot delete trigger")
        return json.dumps({"errors": [{"message": "Cannot delete trigger"}]}),\
               400


###############################################################################
# IFTTT trigger bunq_balance
###############################################################################

def trigger_balance():
    """ Callback for IFTTT trigger bunq_balance """
    try:
        data = request.get_json()
        print("[trigger_balance] input: {}".format(json.dumps(data)))

        if "triggerFields" not in data or\
                "account" not in data["triggerFields"]:
            print("[trigger_balance] ERROR: account field missing!")
            return json.dumps({"errors": [{"message": "Invalid data"}]}), 400
        account = data["triggerFields"]["account"]
        fields = data["triggerFields"]
        fieldsstr = json.dumps(fields)

        if "trigger_identity" not in data:
            print("[trigger_balance] ERROR: trigger_identity field missing!")
            return json.dumps({"errors": [{"message": "Invalid data"}]}), 400
        identity = data["trigger_identity"]

        limit = 50
        if "limit" in data:
            limit = data["limit"]

        if account == "NL42BUNQ0123456789":
            return trigger_balance_test(limit)

        timezone = "UTC"
        if "user" in data and "timezone" in data["user"]:
            timezone = data["user"]["timezone"]

        entity = storage.retrieve("trigger_balance", identity)
        if entity is not None:
            if entity["account"] != account or \
                    json.dumps(entity["fields"]) != fieldsstr:
                storage.store("trigger_balance", identity, {
                    "account": account,
                    "identity": identity,
                    "fields": fields
                })
                print("[trigger_balance] updating trigger {} {}"
                      .format(account, fieldsstr))
        else:
            storage.store("trigger_balance", identity, {
                "account": account,
                "identity": identity,
                "fields": fields
            })
            storage.store("balance_"+identity, "0", {"value": {
                "created_at": "2018-01-05T11:25:15+00:00",
                "account": account,
                "balance": "0.00",
                "meta": {
                    "id": "0",
                    "timestamp": "1515151515"
                }
            }})
            print("[trigger_balance] storing new trigger {} {}"
                  .format(account, fieldsstr))

        transactions = []
        for entity in storage.query_all("balance_" + identity):
            entity["value"]["created_at"] = arrow.get(\
                entity["value"]["created_at"]).to(timezone).isoformat()
            transactions.append(entity["value"])
        transactions = sorted(transactions,
                              key=lambda k: -int(k["meta"]["timestamp"]))

        if len(transactions) > 50:
            for trans in transactions[50:]:
                storage.remove("balance_"+identity, str(trans["meta"]["id"]))

        print("[trigger_balance] Found {} transactions"
              .format(len(transactions)))
        return json.dumps({"data": transactions[:limit]})
    except Exception:
        traceback.print_exc()
        print("[trigger_balance] ERROR: cannot retrieve balances")
        return json.dumps({"errors": [{"message": \
                           "Cannot retrieve balances"}]}), 400


def trigger_balance_test(limit):
    """ Test data for IFTTT trigger bunq_balance """
    result = [{
        "created_at": "2018-01-05T11:25:15+00:00",
        "account": "NL42BUNQ0123456789",
        "balance": "15.15",
        "meta": {
            "id": "1",
            "timestamp": "1515151515"
        }
    }, {
        "created_at": "2014-10-24T09:03:34+00:00",
        "account": "NL42BUNQ0123456789",
        "balance": "14.14",
        "meta": {
            "id": "2",
            "timestamp": "1414141414"
        }
    }, {
        "created_at": "2008-05-30T04:20:12+00:00",
        "account": "NL42BUNQ0123456789",
        "balance": "12.12",
        "meta": {
            "id": "3",
            "timestamp": "1212121212"
        }
    }]
    return json.dumps({"data": result[:limit]})


def trigger_balance_delete(identity):
    """ Delete a specific trigger identity for IFTTT trigger bunq_balance """
    try:
        for index in storage.query_indexes("balance_"+identity):
            storage.remove("balance_"+identity, index)
        storage.remove("trigger_balance", identity)

        return ""
    except Exception:
        traceback.print_exc()
        print("[trigger_balance_delete] ERROR: cannot delete trigger")
        return json.dumps({"errors": [{"message": "Cannot delete trigger"}]}),\
               400


###############################################################################
# IFTTT trigger bunq_request
###############################################################################

def trigger_request():
    """ Callback for IFTTT trigger bunq_request """
    try:
        data = request.get_json()
        print("[trigger_request] input: {}".format(json.dumps(data)))

        if "triggerFields" not in data or \
                "account" not in data["triggerFields"]:
            print("[trigger_request] ERROR: account field missing!")
            return json.dumps({"errors": [{"message": "Invalid data"}]}), 400
        account = data["triggerFields"]["account"]
        fields = data["triggerFields"]
        fieldsstr = json.dumps(fields)

        if "trigger_identity" not in data:
            print("[trigger_request] ERROR: trigger_identity field missing!")
            return json.dumps({"errors": [{"message": "Invalid data"}]}), 400
        identity = data["trigger_identity"]

        limit = 50
        if "limit" in data:
            limit = data["limit"]

        if account == "NL42BUNQ0123456789":
            return trigger_request_test(limit)

        timezone = "UTC"
        if "user" in data and "timezone" in data["user"]:
            timezone = data["user"]["timezone"]

        entity = storage.retrieve("trigger_request", identity)
        if entity is not None:
            if entity["account"] != account or \
                    json.dumps(entity["fields"]) != fieldsstr:
                storage.store("trigger_request", identity, {
                    "account": account,
                    "identity": identity,
                    "fields": fields
                })
                print("[trigger_request] updating trigger {} {}"
                      .format(account, fieldsstr))
        else:
            storage.store("trigger_request", identity, {
                "account": account,
                "identity": identity,
                "fields": fields
            })
            storage.store("request_"+identity, "0", {"value": {
                "created_at": "2018-01-05T11:25:15+00:00",
                "date": "2018-01-05",
                "amount": "0.00",
                "account": account,
                "counterparty_account": "NL11BANK1111111111",
                "counterparty_name": "Dummy Transaction",
                "description": "This is a dummy transaction",
                "request_id": "123e4567-e89b-12d3-a456-426655440001",
                "meta": {
                    "id": "0",
                    "timestamp": "1515151515"
                }
            }})
            print("[trigger_request] storing new trigger {} {}"
                  .format(account, fieldsstr))

        transactions = []
        for entity in storage.query_all("request_" + identity):
            entity["value"]["created_at"] = arrow.get(\
                entity["value"]["created_at"]).to(timezone).isoformat()
            transactions.append(entity["value"])
        transactions = sorted(transactions,
                              key=lambda k: -int(k["meta"]["timestamp"]))

        if len(transactions) > 50:
            for trans in transactions[50:]:
                storage.remove("request_"+identity, str(trans["meta"]["id"]))

        print("[trigger_request] Found {} transactions"
              .format(len(transactions)))
        return json.dumps({"data": transactions[:limit]})
    except Exception:
        traceback.print_exc()
        print("[trigger_request] ERROR: cannot retrieve requests")
        return json.dumps({"errors": [{"message": \
                           "Cannot retrieve requests"}]}), 400


def trigger_request_test(limit):
    """ Test data for IFTTT trigger bunq_request """
    result = [{
        "created_at": "2018-01-05T11:25:15+00:00",
        "amount": "1.01",
        "account": "NL42BUNQ0123456789",
        "counterparty_account": "NL11BANK1111111111",
        "counterparty_name": "John Doe",
        "description": "Here you are",
        "request_id": "123e4567-e89b-12d3-a456-426655440001",
        "meta": {
            "id": "1",
            "timestamp": "1515151515"
        }
    }, {
        "created_at": "2014-10-24T09:03:34+00:00",
        "amount": "2.02",
        "account": "NL42BUNQ0123456789",
        "counterparty_account": "NL22BANK2222222222",
        "counterparty_name": "Jane Doe",
        "description": "What I owe you",
        "request_id": "123e4567-e89b-12d3-a456-426655440002",
        "meta": {
            "id": "2",
            "timestamp": "1414141414"
        }
    }, {
        "created_at": "2008-05-30T04:20:12+00:00",
        "amount": "-3.03",
        "account": "NL42BUNQ0123456789",
        "counterparty_account": "",
        "counterparty_name": "ACME Store Inc.",
        "description": "POS transaction 1234567890",
        "request_id": "123e4567-e89b-12d3-a456-426655440003",
        "meta": {
            "id": "3",
            "timestamp": "1212121212"
        }
    }]
    return json.dumps({"data": result[:limit]})


def trigger_request_delete(identity):
    """ Delete a specific trigger identity for IFTTT trigger bunq_request """
    try:
        for index in storage.query_indexes("request_"+identity):
            storage.remove("request_"+identity, index)
        storage.remove("trigger_request", identity)

        return ""
    except Exception:
        traceback.print_exc()
        print("[trigger_request_delete] ERROR: cannot delete trigger")
        return json.dumps({"errors": [{"message": "Cannot delete trigger"}]}),\
               400