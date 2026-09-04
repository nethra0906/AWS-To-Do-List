"""
Lambda handler for the serverless to-do list API.

Supported operations (dispatched on API Gateway REST API's `httpMethod`):
    GET     -> list all tasks, oldest first
    POST    -> create a task                {"task": "..."}
    PUT     -> update a task's text/status  {"taskId": "...", "task": "...", "status": "..."}
    DELETE  -> delete a task                {"taskId": "..."}
    OPTIONS -> CORS preflight

Table name and allowed CORS origin are read from environment variables so the
same code works across environments without edits (see template.yaml).
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("TABLE_NAME", "ToDoTable")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
MAX_TASK_LENGTH = 500
ALLOWED_STATUSES = {"pending", "done"}

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


class ValidationError(Exception):
    """Raised for bad client input; always maps to HTTP 400."""


class NotFoundError(Exception):
    """Raised when a taskId doesn't exist; always maps to HTTP 404."""


def lambda_handler(event, context):
    method = event.get("httpMethod", "")

    try:
        if method == "OPTIONS":
            return respond(200, {"message": "CORS OK"})
        if method == "GET":
            return handle_get()
        if method == "POST":
            return handle_post(parse_body(event))
        if method == "PUT":
            return handle_put(parse_body(event))
        if method == "DELETE":
            return handle_delete(parse_body(event))
        return respond(405, {"error": "Method not allowed"})

    except ValidationError as e:
        return respond(400, {"error": str(e)})
    except NotFoundError as e:
        return respond(404, {"error": str(e)})
    except ClientError:
        logger.exception("AWS SDK error handling %s request", method)
        return respond(502, {"error": "A backend service error occurred. Please try again."})
    except Exception:
        logger.exception("Unhandled error handling %s request", method)
        return respond(500, {"error": "An unexpected error occurred. Please try again."})


def parse_body(event):
    raw = event.get("body") or "{}"
    try:
        body = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Request body must be valid JSON") from exc
    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object")
    return body


def validate_task_text(task):
    if not isinstance(task, str):
        raise ValidationError("'task' must be a string")
    task = task.strip()
    if not task:
        raise ValidationError("'task' must not be empty")
    if len(task) > MAX_TASK_LENGTH:
        raise ValidationError(f"'task' must be at most {MAX_TASK_LENGTH} characters")
    return task


def validate_status(status):
    if status not in ALLOWED_STATUSES:
        raise ValidationError(f"'status' must be one of {sorted(ALLOWED_STATUSES)}")
    return status


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def handle_get():
    items = []
    scan_kwargs = {}
    while True:
        result = table.scan(**scan_kwargs)
        items.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    # createdAtSeq is a nanosecond counter used only to break ties reliably;
    # createdAt (ISO string) is what clients should display.
    items.sort(key=lambda item: item.get("createdAtSeq", 0))
    return respond(200, items)


def handle_post(body):
    task = validate_task_text(body.get("task"))
    timestamp = now_iso()
    item = {
        "taskId": str(uuid.uuid4()),
        "task": task,
        "status": "pending",
        "createdAt": timestamp,
        "createdAtSeq": time.time_ns(),
        "updatedAt": timestamp,
    }
    table.put_item(Item=item)
    return respond(201, item)


def handle_put(body):
    task_id = body.get("taskId")
    if not task_id or not isinstance(task_id, str):
        raise ValidationError("'taskId' is required")

    update_names = {"#u": "updatedAt"}
    update_values = {":u": now_iso()}
    set_clauses = ["#u = :u"]

    if "task" in body:
        update_names["#t"] = "task"
        update_values[":t"] = validate_task_text(body.get("task"))
        set_clauses.append("#t = :t")

    if "status" in body:
        update_names["#s"] = "status"
        update_values[":s"] = validate_status(body.get("status"))
        set_clauses.append("#s = :s")

    if len(set_clauses) == 1:
        raise ValidationError("Provide 'task' and/or 'status' to update")

    try:
        result = table.update_item(
            Key={"taskId": task_id},
            UpdateExpression="SET " + ", ".join(set_clauses),
            ExpressionAttributeNames=update_names,
            ExpressionAttributeValues=update_values,
            ConditionExpression="attribute_exists(taskId)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundError(f"No task with id '{task_id}'") from e
        raise

    return respond(200, result.get("Attributes", {}))


def handle_delete(body):
    task_id = body.get("taskId")
    if not task_id or not isinstance(task_id, str):
        raise ValidationError("'taskId' is required")

    try:
        table.delete_item(
            Key={"taskId": task_id},
            ConditionExpression="attribute_exists(taskId)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundError(f"No task with id '{task_id}'") from e
        raise

    return respond(200, {"deleted": task_id})


class DecimalEncoder(json.JSONEncoder):
    """DynamoDB returns numbers as Decimal; json.dumps can't handle those natively."""

    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


def respond(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": json.dumps(body, cls=DecimalEncoder),
    }
