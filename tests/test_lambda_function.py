"""
Unit tests for lambda_function.py using moto to mock DynamoDB.

Run with:
    pip install -r requirements-dev.txt
    pytest
"""

import json
import os

import boto3
import pytest
from moto import mock_aws

TABLE_NAME = "ToDoTableTest"


@pytest.fixture
def lambda_module(monkeypatch):
    """Import lambda_function fresh, against a mocked DynamoDB table."""
    monkeypatch.setenv("TABLE_NAME", TABLE_NAME)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        boto3.resource("dynamodb", region_name="us-east-1").create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "taskId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "taskId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        import importlib
        import lambda_function

        importlib.reload(lambda_function)
        yield lambda_function


def make_event(method, body=None):
    return {"httpMethod": method, "body": json.dumps(body) if body is not None else None}


def test_options_returns_cors_ok(lambda_module):
    resp = lambda_module.lambda_handler(make_event("OPTIONS"), None)
    assert resp["statusCode"] == 200
    assert resp["headers"]["Access-Control-Allow-Origin"] == "*"


def test_get_empty_list(lambda_module):
    resp = lambda_module.lambda_handler(make_event("GET"), None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"]) == []


def test_post_creates_task(lambda_module):
    resp = lambda_module.lambda_handler(make_event("POST", {"task": "Buy milk"}), None)
    assert resp["statusCode"] == 201
    body = json.loads(resp["body"])
    assert body["task"] == "Buy milk"
    assert body["status"] == "pending"
    assert "taskId" in body
    assert "createdAt" in body


def test_post_rejects_empty_task(lambda_module):
    resp = lambda_module.lambda_handler(make_event("POST", {"task": "   "}), None)
    assert resp["statusCode"] == 400


def test_post_rejects_missing_task(lambda_module):
    resp = lambda_module.lambda_handler(make_event("POST", {}), None)
    assert resp["statusCode"] == 400


def test_post_rejects_oversized_task(lambda_module):
    resp = lambda_module.lambda_handler(make_event("POST", {"task": "x" * 501}), None)
    assert resp["statusCode"] == 400


def test_get_returns_created_tasks_sorted(lambda_module):
    lambda_module.lambda_handler(make_event("POST", {"task": "first"}), None)
    lambda_module.lambda_handler(make_event("POST", {"task": "second"}), None)

    resp = lambda_module.lambda_handler(make_event("GET"), None)
    items = json.loads(resp["body"])
    assert [i["task"] for i in items] == ["first", "second"]


def test_put_updates_status(lambda_module):
    created = json.loads(
        lambda_module.lambda_handler(make_event("POST", {"task": "task"}), None)["body"]
    )
    resp = lambda_module.lambda_handler(
        make_event("PUT", {"taskId": created["taskId"], "status": "done"}), None
    )
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["status"] == "done"


def test_put_updates_task_text(lambda_module):
    created = json.loads(
        lambda_module.lambda_handler(make_event("POST", {"task": "old text"}), None)["body"]
    )
    resp = lambda_module.lambda_handler(
        make_event("PUT", {"taskId": created["taskId"], "task": "new text"}), None
    )
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["task"] == "new text"


def test_put_rejects_invalid_status(lambda_module):
    created = json.loads(
        lambda_module.lambda_handler(make_event("POST", {"task": "task"}), None)["body"]
    )
    resp = lambda_module.lambda_handler(
        make_event("PUT", {"taskId": created["taskId"], "status": "archived"}), None
    )
    assert resp["statusCode"] == 400


def test_put_missing_task_returns_404(lambda_module):
    resp = lambda_module.lambda_handler(
        make_event("PUT", {"taskId": "does-not-exist", "status": "done"}), None
    )
    assert resp["statusCode"] == 404


def test_delete_removes_task(lambda_module):
    created = json.loads(
        lambda_module.lambda_handler(make_event("POST", {"task": "task"}), None)["body"]
    )
    resp = lambda_module.lambda_handler(
        make_event("DELETE", {"taskId": created["taskId"]}), None
    )
    assert resp["statusCode"] == 200

    remaining = json.loads(lambda_module.lambda_handler(make_event("GET"), None)["body"])
    assert remaining == []


def test_delete_missing_task_returns_404(lambda_module):
    resp = lambda_module.lambda_handler(make_event("DELETE", {"taskId": "nope"}), None)
    assert resp["statusCode"] == 404


def test_unsupported_method_returns_405(lambda_module):
    resp = lambda_module.lambda_handler(make_event("PATCH"), None)
    assert resp["statusCode"] == 405


def test_malformed_json_body_returns_400(lambda_module):
    event = {"httpMethod": "POST", "body": "{not json"}
    resp = lambda_module.lambda_handler(event, None)
    assert resp["statusCode"] == 400
