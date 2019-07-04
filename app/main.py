"""
Main module serving the pages for the bunq2IFTTT appengine app
"""

import json
import os

from flask import Flask, request, render_template

import auth
import event
import payment
import storage
import util

# pylint: disable=invalid-name
app = Flask(__name__)
# pylint: enable=invalid-name


###############################################################################
# Webpages
###############################################################################

@app.route("/")
def home_get():
    """ Endpoint for the homepage """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("start.html")
    iftttkeyset = (util.get_ifttt_service_key() is not None)
    bunqkeymode = util.get_bunq_security_mode()
    accounts = util.get_bunq_accounts_combined()
    appmode = util.get_app_mode()
    masterurl = util.get_app_master_url()
    enableexternal = util.get_external_payment_enabled()
    # Google AppEngine does not provide fixed ip addresses
    defaultallips = (os.getenv("GAE_INSTANCE") is not None)
    return render_template("main.html",\
        iftttkeyset=iftttkeyset, bunqkeymode=bunqkeymode, accounts=accounts,\
        appmode=appmode, masterurl=masterurl, enableexternal=enableexternal,\
        defaultallips=defaultallips)


@app.route("/login", methods=["POST"])
def user_login():
    """ Endpoint for login password submission """
    return auth.user_login()


@app.route("/set_ifttt_service_key", methods=["POST"])
def set_ifttt_service_key():
    """ Endpoint for IFTTT service key submission """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    return auth.set_ifttt_service_key()

@app.route("/set_bunq_oauth_api_key", methods=["POST"])
def set_bunq_oauth_api_key():
    """ Endpoint for bunq OAuth keys / API key submission """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    return auth.set_bunq_oauth_api_key()

@app.route("/auth", methods=["GET"])
def set_bunq_oauth_response():
    """ Endpoint for the bunq OAuth response """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    return auth.set_bunq_oauth_response()

@app.route("/update_accounts", methods=["GET"])
def update_accounts():
    """ Endpoint to update the list of bunq accounts """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    util.update_bunq_accounts()
    return render_template("message.html", msgtype="success", msg=\
        'Account update completed<br><br>'\
        '<a href="/">Click here to return home</a>')

@app.route("/mode_master", methods=["GET"])
def mode_master():
    """ Endpoint to switch to master mode """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    util.save_app_mode('master')
    return render_template("message.html", msgtype="success", msg=\
        'Master mode set<br><br>'\
        '<a href="/">Click here to return home</a>')

@app.route("/account_change_internal", methods=["GET"])
def account_change_internal():
    """ Enable/disable an account for internal payments """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    if util.change_account_enabled_local(request.args["iban"],
                                         "enableInternal",
                                         request.args["value"]):
        return render_template("message.html", msgtype="success", msg=\
            'Status changed<br><br>'\
            '<a href="/">Click here to return home</a>')
    return render_template("message.html", msgtype="danger", msg=\
        'Something went wrong, please check the logs!<br><br>'\
        '<a href="/">Click here to return home</a>')

@app.route("/account_change_draft", methods=["GET"])
def account_change_draft():
    """ Enable/disable an account for draft payments """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    if util.change_account_enabled_local(request.args["iban"],
                                         "enableDraft",
                                         request.args["value"]):
        return render_template("message.html", msgtype="success", msg=\
            'Status changed<br><br>'\
            '<a href="/">Click here to return home</a>')
    return render_template("message.html", msgtype="danger", msg=\
        'Something went wrong, please check the logs!<br><br>'\
        '<a href="/">Click here to return home</a>')

@app.route("/account_change_external", methods=["GET"])
def account_change_external():
    """ Enable/disable an account for external payments """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    if not util.get_external_payment_enabled():
        return render_template("message.html", msgtype="danger", msg=\
            'External payments are disabled!<br><br>'\
            '<a href="/">Click here to return home</a>')
    if util.change_account_enabled_local(request.args["iban"],
                                         "enableExternal",
                                         request.args["value"]):
        return render_template("message.html", msgtype="success", msg=\
            'Status changed<br><br>'\
            '<a href="/">Click here to return home</a>')
    return render_template("message.html", msgtype="danger", msg=\
        'Something went wrong, please check the logs!<br><br>'\
        '<a href="/">Click here to return home</a>')

@app.route("/account_change_mutation", methods=["GET"])
def account_change_mutation():
    """ Enable/disable an account for mutation/balance triggers """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    if util.get_bunq_security_mode() == "OAuth":
        return render_template("message.html", msgtype="danger", msg=\
            'Callbacks can only be set with an API key!<br><br>'\
            '<a href="/">Click here to return home</a>')
    if util.change_account_enabled_callback(request.args["iban"],
                                            "enableMutation",
                                            request.args["value"]):
        return render_template("message.html", msgtype="success", msg=\
            'Status changed<br><br>'\
            '<a href="/">Click here to return home</a>')
    return render_template("message.html", msgtype="danger", msg=\
        'Something went wrong, please check the logs!<br><br>'\
        '<a href="/">Click here to return home</a>')

@app.route("/account_change_request", methods=["GET"])
def account_change_request():
    """ Enable/disable an account for request triggers """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    if util.get_bunq_security_mode() == "OAuth":
        return render_template("message.html", msgtype="danger", msg=\
            'Callbacks can only be set with an API key!<br><br>'\
            '<a href="/">Click here to return home</a>')
    if util.change_account_enabled_callback(request.args["iban"],
                                            "enableRequest",
                                            request.args["value"]):
        return render_template("message.html", msgtype="success", msg=\
            'Status changed<br><br>'\
            '<a href="/">Click here to return home</a>')
    return render_template("message.html", msgtype="danger", msg=\
        'Something went wrong, please check the logs!<br><br>'\
        '<a href="/">Click here to return home</a>')

@app.route("/mode_slave", methods=["GET"])
def mode_slave():
    """ Endpoint to switch to slave mode """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    util.save_app_mode('slave')
    return render_template("message.html", msgtype="success", msg=\
        'Slave mode set<br><br>'\
        '<a href="/">Click here to return home</a><br>'\
        'Please make sure to set the URL to the master instance!')

@app.route("/set_master_url", methods=["POST"])
def set_master_url():
    """ Endpoint to set the master URL used in slave mode """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    url = request.form["masterurl"]
    if not url.startswith("http://") and not url.startswith("https://"):
        return render_template("message.html", msgtype="danger", msg=\
            'Invalid URL, it doesnt start with http(s)://<br><br>'\
            '<a href="/">Click here to return home</a><br>')
    if not url.endswith("/"):
        url += "/"
    util.save_app_master_url(url)
    return render_template("message.html", msgtype="success", msg=\
        'Master URL set<br><br>'\
        '<a href="/">Click here to return home</a><br>')

@app.route("/account_callback", methods=["POST"])
def account_callback():
    """ Callback for submitting account info from a slave """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401

    data = request.get_json()
    print("Input: ", json.dumps(data))
    util.process_bunq_accounts_callback(data)

    return ""


###############################################################################
# Helper methods
###############################################################################

def check_ifttt_service_key():
    """ Helper method to check the IFTTT-Service-Key header """
    if "IFTTT-Service-Key" not in request.headers or \
            request.headers["IFTTT-Service-Key"] \
            != util.get_ifttt_service_key():
        return json.dumps({"errors": [{"message": "Invalid IFTTT key"}]})
    return None


###############################################################################
# Cron endpoints
###############################################################################

@app.route("/cron/clean_seen")
def clean_seen():
    """ Clean the seen cache periodically """
    if os.getenv("GAE_INSTANCE") is not None:
        if "X-Appengine-Cron" not in request.headers\
        or request.headers["X-Appengine-Cron"] != "true":
            print("Invalid cron call")
            return "Invalid cron call"
    else:
        host = request.host
        if host.find(":") > -1:
            host = host[:host.find(":")]
        if host not in ["127.0.0.1", "localhost"]:
            return "Invalid cron call"

    storage.clean_seen("seen_mutation")
    storage.clean_seen("seen_request")
    return ""


###############################################################################
# Status / testing endpoints
###############################################################################

@app.route("/ifttt/v1/status")
def ifttt_status():
    """ Status endpoint for IFTTT platform endpoint tests """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401

    return ""

@app.route("/ifttt/v1/test/setup", methods=["POST"])
def ifttt_test_setup():
    """ Testdata endpoint for IFTTT platform endpoint tests """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401

    test_account = "NL42BUNQ0123456789"

    return json.dumps({
        "data": {
            "samples": {
                "triggers": {
                    "bunq_mutation": {
                        "account": test_account,
                        "type": "ANY",
                        "type_2": "ANY",
                        "type_3": "ANY",
                        "type_4": "ANY",
                        "amount_comparator": "above",
                        "amount_value": "0",
                        "amount_comparator_2": "below",
                        "amount_value_2": "99999",
                        "balance_comparator": "above",
                        "balance_value": "0",
                        "balance_comparator_2": "below",
                        "balance_value_2": "99999",
                        "counterparty_name_comparator": "not_equal",
                        "counterparty_name_value": "Foo bar",
                        "counterparty_name_comparator_2": "not_equal",
                        "counterparty_name_value_2": "Foo bar",
                        "counterparty_account_comparator": "not_equal",
                        "counterparty_account_value": "Foo bar",
                        "counterparty_account_comparator_2": "not_equal",
                        "counterparty_account_value_2": "Foo bar",
                        "description_comparator": "not_equal",
                        "description_value": "Foo bar",
                        "description_comparator_2": "not_equal",
                        "description_value_2": "Foo bar",
                    },
                    "bunq_balance": {
                        "account": test_account,
                        "balance_comparator": "above",
                        "balance_value": "0",
                        "balance_comparator_2": "below",
                        "balance_value_2": "99999",
                    },
                    "bunq_request": {
                        "account": test_account,
                        "amount_comparator": "above",
                        "amount_value": "0",
                        "amount_comparator_2": "below",
                        "amount_value_2": "99999",
                        "counterparty_name_comparator": "not_equal",
                        "counterparty_name_value": "Foo bar",
                        "counterparty_name_comparator_2": "not_equal",
                        "counterparty_name_value_2": "Foo bar",
                        "counterparty_account_comparator": "not_equal",
                        "counterparty_account_value": "Foo bar",
                        "counterparty_account_comparator_2": "not_equal",
                        "counterparty_account_value_2": "Foo bar",
                        "description_comparator": "not_equal",
                        "description_value": "Foo bar",
                        "description_comparator_2": "not_equal",
                        "description_value_2": "Foo bar",
                    },
                },
                "actions": {
                    "bunq_internal_payment": {
                        "amount": "1.23",
                        "source_account": test_account,
                        "target_account": test_account,
                        "description": "x",
                    },
                    "bunq_external_payment": {
                        "amount": "1.23",
                        "source_account": test_account,
                        "target_account": test_account,
                        "target_name": "John Doe",
                        "description": "x",
                    },
                    "bunq_draft_payment": {
                        "amount": "1.23",
                        "source_account": test_account,
                        "target_account": test_account,
                        "target_name": "John Doe",
                        "description": "x",
                    },
                },
                "actionRecordSkipping": {
                    "bunq_internal_payment": {
                        "amount": "-1.23",
                        "source_account": test_account,
                        "target_account": test_account,
                        "description": "x",
                    },
                    "bunq_external_payment": {
                        "amount": "-1.23",
                        "source_account": test_account,
                        "target_account": test_account,
                        "target_name": "John Doe",
                        "description": "x",
                    },
                    "bunq_draft_payment": {
                        "amount": "-1.23",
                        "source_account": test_account,
                        "target_account": test_account,
                        "target_name": "John Doe",
                        "description": "x",
                    },
                }
            }
        }
    })


###############################################################################
# Option value endpoints
###############################################################################

@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "amount_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "amount_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "balance_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "balance_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_balance/fields/"\
           "balance_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_balance/fields/"\
           "balance_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "amount_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "amount_comparator_2/options", methods=["POST"])
def ifttt_comparator_numeric_options():
    """ Option values for numeric comparators """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401

    data = {"data": [
        {"value": "ignore", "label": "ignore"},
        {"value": "equal", "label": "equal to"},
        {"value": "not_equal", "label": "not equal to"},
        {"value": "above", "label": "above"},
        {"value": "above_equal", "label": "above or equal to"},
        {"value": "below", "label": "below"},
        {"value": "below_equal", "label": "below or equal to"},
        {"value": "in", "label": "in [json array]"},
        {"value": "not_in", "label": "not in [json array]"},
    ]}
    return json.dumps(data)

@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "counterparty_name_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "counterparty_name_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "counterparty_account_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "counterparty_account_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "description_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "description_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "counterparty_name_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "counterparty_name_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "counterparty_account_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "counterparty_account_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "description_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "description_comparator_2/options", methods=["POST"])
def ifttt_comparator_alpha_options():
    """ Option values for alphanumeric comparators """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401

    data = {"data": [
        {"value": "ignore", "label": "ignore"},
        {"value": "equal", "label": "is equal to"},
        {"value": "not_equal", "label": "is not equal to"},
        {"value": "cont", "label": "contains"},
        {"value": "not_cont", "label": "does not contain"},
        {"value": "equal_nc", "label": "is equal to (ignore case)"},
        {"value": "not_equal_nc", "label": "is not equal to (ignore case)"},
        {"value": "cont_nc", "label": "contains (ignore case)"},
        {"value": "not_cont_nc", "label": "does not contain (ignore case)"},
        {"value": "in", "label": "in [json array]"},
        {"value": "not_in", "label": "not in [json array]"},
        {"value": "in_nc", "label": "in [json array] (ignore case)"},
        {"value": "not_in_nc", "label": "not in [json array] (ignore case)"},
    ]}
    return json.dumps(data)

@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "type/options", methods=["POST"])
def ifttt_type_options_1():
    """ Option values for the first type field """
    return ifttt_type_options(True)

@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "type_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "type_3/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "type_4/options", methods=["POST"])
def ifttt_type_options_2():
    """ Option values for the subsequent type fields """
    return ifttt_type_options(False)

def ifttt_type_options(first):
    """ Option values for the type fields """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401

    if first:
        data = {"data": [{"value": "ANY", "label": "ANY"}]}
    else:
        data = {"data": [{"value": "---", "label": "---"}]}

    data["data"].extend([
        {"value": "BUNQ", "label": "BUNQ (all subtypes)"},
        {"value": "BUNQ_BILLING", "label": "BUNQ_BILLING"},
        {"value": "BUNQ_INTEREST", "label": "BUNQ_INTEREST"},
        {"value": "BUNQ_REWARD", "label": "BUNQ_REWARD"},
        {"value": "CARD", "label": "CARD (all subtypes)"},
        {"value": "CARD_PAYMENT", "label": "CARD_PAYMENT"},
        {"value": "CARD_REVERSAL", "label": "CARD_REVERSAL"},
        {"value": "CARD_WITHDRAWAL", "label": "CARD_WITHDRAWAL"},
        {"value": "ONLINE", "label": "ONLINE (all subtypes)"},
        {"value": "ONLINE_IDEAL", "label": "ONLINE_IDEAL"},
        {"value": "ONLINE_SOFORT", "label": "ONLINE_SOFORT"},
        {"value": "TRANSFER", "label": "TRANSFER (all subtypes"},
        {"value": "TRANSFER_REGULAR", "label": "TRANSFER_REGULAR"},
        {"value": "TRANSFER_REQUEST", "label": "TRANSFER_REQUEST"},
        {"value": "TRANSFER_SAVINGS", "label": "TRANSFER_SAVINGS"},
        {"value": "TRANSFER_SCHEDULED", "label": "TRANSFER_SCHEDULED"},
    ])
    return json.dumps(data)


@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "account/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_balance/fields/"\
           "account/options", methods=["POST"])
def ifttt_account_options_mutation():
    """ Option values for mutation/balance trigger account selection"""
    return ifttt_account_options(True, False, "enableMutation")

@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "account/options", methods=["POST"])
def ifttt_account_options_request():
    """ Option values for request trigger account selection"""
    return ifttt_account_options(True, False, "enableRequest")

@app.route("/ifttt/v1/actions/bunq_internal_payment/fields/"\
           "source_account/options", methods=["POST"])
def ifttt_account_options_internal_source():
    """ Option values for internal payment source account selection"""
    return ifttt_account_options(False, True, "enableInternal")

@app.route("/ifttt/v1/actions/bunq_internal_payment/fields/"\
           "target_account/options", methods=["POST"])
def ifttt_account_options_internal_target():
    """ Option values for internal payment target account selection"""
    return ifttt_account_options(False, True, None)

@app.route("/ifttt/v1/actions/bunq_draft_payment/fields/"\
           "source_account/options", methods=["POST"])
def ifttt_account_options_draft():
    """ Option values for draft payment source account selection"""
    return ifttt_account_options(False, True, "enableDraft")

@app.route("/ifttt/v1/actions/bunq_external_payment/fields/"\
           "source_account/options", methods=["POST"])
def ifttt_account_options_external():
    """ Option values for draft payment source account selection"""
    return ifttt_account_options(False, True, "enableExternal")


def ifttt_account_options(include_any, local, enable_key):
    """ Option values for account selection """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401

    if local:
        accounts = util.get_bunq_accounts_local()
    else:
        accounts = util.get_bunq_accounts_callback()

    if include_any:
        data = {"data": [{"label": "ANY", "value": "ANY"}]}
    else:
        data = {"data": []}

    for acc in accounts:
        if enable_key is None or acc[enable_key]:
            ibanstr = acc["iban"]
            iban_formatted = ""
            while len(ibanstr) > 4:
                iban_formatted += ibanstr[:4] + " "
                ibanstr = ibanstr[4:]
            iban_formatted += ibanstr
            data["data"].append({
                "label": "{} ({})".format(acc["description"],
                                          iban_formatted),
                "value": acc["iban"]
            })
    return json.dumps(data)


###############################################################################
# Bunq callback endpoints
###############################################################################

@app.route("/bunq_callback_mutation", methods=["POST"])
@app.route("/bunq2ifttt_mutation", methods=["POST"])
def bunq2ifttt_mutation():
    """ Callback for bunq MUTATION events """
    return "", event.bunq_callback_mutation()

@app.route("/bunq_callback_request", methods=["POST"])
@app.route("/bunq2ifttt_request", methods=["POST"])
def bunq2ifttt_request():
    """ Callback for bunq REQUEST events """
    return "", event.bunq_callback_request()


###############################################################################
# Event trigger endpoints
###############################################################################

@app.route("/ifttt/v1/triggers/bunq_mutation", methods=["POST"])
def trigger_mutation():
    """ Retrieve bunq_mutation trigger items """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_mutation()

@app.route("/ifttt/v1/triggers/bunq_mutation/trigger_identity/<triggerid>",
           methods=["DELETE"])
def trigger_mutation_delete(triggerid):
    """ Delete a trigger_identity for the bunq_mutation trigger """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_mutation_delete(triggerid)

@app.route("/ifttt/v1/triggers/bunq_balance", methods=["POST"])
def trigger_balance():
    """ Retrieve bunq_balance trigger items """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_balance()

@app.route("/ifttt/v1/triggers/bunq_balance/trigger_identity/<triggerid>",
           methods=["DELETE"])
def trigger_balance_delete(triggerid):
    """ Delete a trigger_identity for the bunq_balance trigger """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_balance_delete(triggerid)

@app.route("/ifttt/v1/triggers/bunq_request", methods=["POST"])
def trigger_request():
    """ Retrieve bunq_balance trigger items """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_request()

@app.route("/ifttt/v1/triggers/bunq_request/trigger_identity/<triggerid>",
           methods=["DELETE"])
def trigger_request_delete(triggerid):
    """ Delete a trigger_identity for the bunq_request trigger """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_request_delete(triggerid)


###############################################################################
# Payment action endpoints
###############################################################################

@app.route("/ifttt/v1/actions/bunq_internal_payment", methods=["POST"])
def ifttt_internal_payment():
    """ Execute an internal payment action """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return payment.ifttt_bunq_payment(internal=True, draft=False)

@app.route("/ifttt/v1/actions/bunq_external_payment", methods=["POST"])
def ifttt_external_payment():
    """ Execute an external payment action """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return payment.ifttt_bunq_payment(internal=False, draft=False)

@app.route("/ifttt/v1/actions/bunq_draft_payment", methods=["POST"])
def ifttt_draft_payment():
    """ Execute an draft payment action """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return payment.ifttt_bunq_payment(internal=False, draft=True)


###############################################################################
# Standalone running
###############################################################################

if __name__ == "__main__":
    app.run(host="localhost", port=18000, debug=True)
