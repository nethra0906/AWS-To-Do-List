import json
import boto3
import uuid

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('ToDoTable')

def lambda_handler(event, context):
    print("Event:", event)
    method = event.get('httpMethod', '')

    if method == 'OPTIONS':
        return respond(200, {"message": "CORS OK"})

    try:
        if method == 'POST':
            body = json.loads(event['body'])
            task_id = str(uuid.uuid4())
            item = {
                'taskId': task_id,
                'task': body['task'],
                'status': 'pending'
            }
            table.put_item(Item=item)
            return respond(200, item)

        elif method == 'GET':
            result = table.scan()
            items = result.get('Items', [])
          
            return respond(200, items)

        elif method == 'PUT':
            body = json.loads(event['body'])
            task_id = body.get('taskId')
            status = body.get('status', 'pending')
            table.update_item(
                Key={'taskId': task_id},
                UpdateExpression="set #s = :s",
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={':s': status}
            )
            return respond(200, {"taskId": task_id, "status": status})

        elif method == 'DELETE':
            body = json.loads(event['body'])
            task_id = body.get('taskId')
            table.delete_item(Key={'taskId': task_id})
            return respond(200, {"deleted": task_id})

        else:
            return respond(405, {"error": "Method Not Allowed"})

    except Exception as e:
        print("Error:", str(e))
        return respond(500, {"error": str(e)})

def respond(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps(body)
    }
