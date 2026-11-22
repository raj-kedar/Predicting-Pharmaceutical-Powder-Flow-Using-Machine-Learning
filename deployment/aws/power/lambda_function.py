"""
One switch for the FlowLytix server and database.

Commands: {"action": "stop"}, {"action": "start"}, {"action": "status"}.
A 5-minute schedule calls this with no action and moves one safe step at a time:
  stop:  server first, then database (and re-stops the database after AWS's 7-day restart)
  start: database first, then server
"""
import html
import json
import os

STOPPED, STARTING, RUNNING = "stopped", "starting", "running"


def decide(desired, server, database):
    """Return (step, next_desired). Pure logic, so every state can be tested."""
    if desired == STOPPED:
        if server == "running":
            return "stop_server", STOPPED
        if server == "stopped" and database == "available":
            return "stop_database", STOPPED
        return None, STOPPED
    if desired == STARTING:
        if database == "stopped":
            return "start_database", STARTING
        if database == "available" and server == "stopped":
            return "start_server", STARTING
        if database == "available" and server == "running":
            return None, RUNNING
        return None, STARTING
    return None, RUNNING


def _clients():
    import boto3
    return boto3.client("ec2"), boto3.client("rds"), boto3.client("ssm")


def _button(label, arn, action, primary=False, confirm=None):
    css = "btn btn-primary" if primary else "btn"
    prompt = f' confirmation="{html.escape(confirm, quote=True)}"' if confirm else ""
    return (f'<a class="{css}">{html.escape(label)}</a>'
            f'<cwdb-action action="call" endpoint="{html.escape(arn, quote=True)}"{prompt}>'
            f'{json.dumps({"action": action})}</cwdb-action> ')


def render_widget(result, arn):
    """HTML for the CloudWatch dashboard, with buttons that call this function."""
    if not result.get("ok"):
        return f"<p><b>Error:</b> {html.escape(str(result.get('error')))}</p>"
    mode, server, database = result["mode"], result["server"], result["database"]
    if mode == RUNNING and server == "running" and database == "available":
        headline = "ONLINE"
    elif mode == STOPPED and server == "stopped" and database == "stopped":
        headline = "STOPPED"
    elif mode == STOPPED:
        headline = "STOPPING (allow about 15 minutes)"
    elif mode == STARTING:
        headline = "STARTING (allow about 15 minutes)"
    else:
        headline = "CHECK STATUS"
    buttons = _button("Refresh", arn, "status")
    if mode != STOPPED:
        buttons += _button("Stop FlowLytix", arn, "stop", confirm="Stop FlowLytix? The website and payments will be offline.")
    if mode != RUNNING:
        buttons += _button("Start FlowLytix", arn, "start", primary=True, confirm="Start FlowLytix?")
    return (f"<h2>FlowLytix: {html.escape(headline)}</h2>"
            f"<p>Server: <b>{html.escape(server)}</b> &nbsp; Database: <b>{html.escape(database)}</b></p>"
            f"<p>{buttons}</p>"
            "<p>Use these buttons instead of starting or stopping the resources by hand. "
            "While stopped, the database is kept stopped automatically.</p>")


def lambda_handler(event, context, clients=None):
    event = event or {}
    if "widgetContext" in event:      # opened or clicked from the CloudWatch dashboard
        request = {"action": event.get("action") or "status"}
        return render_widget(_run(request, clients), context.invoked_function_arn)
    return _run(event, clients)


def _run(event, clients=None):
    ec2, rds, ssm = clients or _clients()
    instance = os.environ["INSTANCE_ID"]
    db_id = os.environ["DB_ID"]
    parameter = os.environ["STATE_PARAMETER"]
    action = event.get("action")
    if action not in (None, "start", "stop", "status"):
        return {"ok": False, "error": "action must be start, stop or status"}

    desired = ssm.get_parameter(Name=parameter)["Parameter"]["Value"]
    if action == "stop":
        desired = STOPPED
    elif action == "start":
        desired = STARTING

    server = ec2.describe_instances(InstanceIds=[instance])["Reservations"][0]["Instances"][0]["State"]["Name"]
    database = rds.describe_db_instances(DBInstanceIdentifier=db_id)["DBInstances"][0]["DBInstanceStatus"]
    if action == "status":
        return {"ok": True, "mode": desired, "server": server, "database": database}

    step, next_desired = decide(desired, server, database)
    if step == "stop_server":
        ec2.stop_instances(InstanceIds=[instance])
    elif step == "start_server":
        ec2.start_instances(InstanceIds=[instance])
    elif step == "stop_database":
        rds.stop_db_instance(DBInstanceIdentifier=db_id)
    elif step == "start_database":
        rds.start_db_instance(DBInstanceIdentifier=db_id)
    ssm.put_parameter(Name=parameter, Value=next_desired, Type="String", Overwrite=True)
    result = {"ok": True, "mode": next_desired, "server": server, "database": database, "step": step}
    print(json.dumps(result))
    return result
