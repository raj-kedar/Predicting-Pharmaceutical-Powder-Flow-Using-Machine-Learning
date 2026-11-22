import importlib.util

import pytest

from src.config import ROOT

spec = importlib.util.spec_from_file_location(
    "flowlytix_power", ROOT / "deployment" / "aws" / "power" / "lambda_function.py")
power = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power)


@pytest.mark.parametrize("desired,server,database,step,after", [
    ("stopped", "running", "available", "stop_server", "stopped"),
    ("stopped", "stopping", "available", None, "stopped"),
    ("stopped", "stopped", "available", "stop_database", "stopped"),   # includes AWS's 7-day restart
    ("stopped", "stopped", "stopping", None, "stopped"),
    ("stopped", "stopped", "stopped", None, "stopped"),
    ("starting", "stopped", "stopped", "start_database", "starting"),
    ("starting", "stopped", "starting", None, "starting"),
    ("starting", "stopped", "available", "start_server", "starting"),
    ("starting", "pending", "available", None, "starting"),
    ("starting", "running", "available", None, "running"),
    ("running", "stopped", "stopped", None, "running"),                # never fights a manual stop
    ("running", "running", "available", None, "running"),
])
def test_every_power_state(desired, server, database, step, after):
    assert power.decide(desired, server, database) == (step, after)


class Fake:
    def __init__(self, server="running", database="available", mode="running"):
        self.server, self.database, self.mode, self.calls = server, database, mode, []

    def get_parameter(self, Name):
        return {"Parameter": {"Value": self.mode}}

    def put_parameter(self, **kwargs):
        self.mode = kwargs["Value"]

    def describe_instances(self, InstanceIds):
        return {"Reservations": [{"Instances": [{"State": {"Name": self.server}}]}]}

    def describe_db_instances(self, DBInstanceIdentifier):
        return {"DBInstances": [{"DBInstanceStatus": self.database}]}

    def stop_instances(self, InstanceIds):
        self.calls.append(("stop_server", InstanceIds))

    def start_instances(self, InstanceIds):
        self.calls.append(("start_server", InstanceIds))

    def stop_db_instance(self, DBInstanceIdentifier):
        self.calls.append(("stop_database", DBInstanceIdentifier))

    def start_db_instance(self, DBInstanceIdentifier):
        self.calls.append(("start_database", DBInstanceIdentifier))


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("INSTANCE_ID", "i-flowlytix")
    monkeypatch.setenv("DB_ID", "flowlytix-db")
    monkeypatch.setenv("STATE_PARAMETER", "/flowlytix/power_mode")


def run(fake, event):
    return power.lambda_handler(event, None, clients=(fake, fake, fake))


def test_status_changes_nothing():
    fake = Fake()
    assert run(fake, {"action": "status"})["server"] == "running"
    assert fake.calls == [] and fake.mode == "running"


def test_stop_targets_only_flowlytix_server():
    fake = Fake()
    run(fake, {"action": "stop"})
    assert fake.calls == [("stop_server", ["i-flowlytix"])] and fake.mode == "stopped"


def test_schedule_restops_database_after_aws_restart():
    fake = Fake(server="stopped", database="available", mode="stopped")
    run(fake, {"source": "aws.events"})
    assert fake.calls == [("stop_database", "flowlytix-db")]


def test_start_begins_with_database():
    fake = Fake(server="stopped", database="stopped", mode="stopped")
    run(fake, {"action": "start"})
    assert fake.calls == [("start_database", "flowlytix-db")] and fake.mode == "starting"


class Context:
    invoked_function_arn = "arn:aws:lambda:ap-south-1:1:function:flowlytix-power"


def widget(fake, **event):
    return power.lambda_handler({"widgetContext": {}, **event}, Context(), clients=(fake, fake, fake))


def test_opening_dashboard_never_changes_anything():
    fake = Fake(server="stopped", database="available", mode="stopped")
    page = widget(fake)
    assert fake.calls == [] and "STOPPING" in page and "Start FlowLytix" in page


def test_dashboard_stop_button_requires_confirmation():
    page = widget(Fake())
    assert "ONLINE" in page and "Stop FlowLytix" in page and 'confirmation="' in page
    assert "Start FlowLytix" not in page


def test_dashboard_buttons_work():
    fake = Fake()
    assert "STOPPING" in widget(fake, action="stop")
    assert fake.calls == [("stop_server", ["i-flowlytix"])]


def test_dashboard_rejects_unknown_action():
    fake = Fake()
    assert "Error" in widget(fake, action="terminate") and fake.calls == []


def test_unknown_action_does_nothing():
    fake = Fake()
    assert run(fake, {"action": "terminate"})["ok"] is False
    assert fake.calls == []
