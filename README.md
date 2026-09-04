# 📝 AWS Serverless To-Do List

A serverless task manager built on API Gateway, Lambda, and DynamoDB, with a
static HTML/CSS/JS frontend hosted on S3. Tasks can be added, edited, marked
done, filtered, and deleted, and every change is persisted in DynamoDB.

## Architecture

```
Browser (index.html/style.css/script.js)
        │  fetch()
        ▼
Amazon API Gateway (REST API)  ── GET / POST / PUT / DELETE / OPTIONS
        │
        ▼
AWS Lambda (lambda_function.py)
        │
        ▼
Amazon DynamoDB (single table, partition key: taskId)
```

The frontend is a static site — it can be hosted from S3, GitHub Pages, or
opened locally — and only ever talks to the API over HTTPS. There is no
server-side rendering and no build step.

## Project layout

| Path | Purpose |
|---|---|
| [index.html](index.html) | App markup |
| [style.css](style.css) | Styling, incl. dark mode & responsive layout |
| [config.js](config.js) | The one line you edit per environment: `API_BASE_URL` |
| [script.js](script.js) | All frontend logic (fetch calls, rendering, state) |
| [lambda_function.py](lambda_function.py) | API backend (CRUD against DynamoDB) |
| [tests/test_lambda_function.py](tests/test_lambda_function.py) | Unit tests for the backend (uses `moto` to mock DynamoDB) |
| [template.yaml](template.yaml) | AWS SAM template that provisions the whole stack |

## Features

- Add, edit, complete/uncomplete, and delete tasks
- Filter by All / Active / Done, with a "clear completed" action
- Optimistic UI updates with rollback on failure
- Loading, empty, and error (with retry) states
- Keyboard-friendly (Enter to add/save, Escape to cancel an edit) and
  screen-reader-friendly (labelled controls, live region for status messages)
- Light/dark theme follows the OS preference
- Task text is always rendered via `textContent`, never `innerHTML`, so task
  content can never execute as HTML/script (stored-XSS safe)

## Backend design notes

- `TABLE_NAME` and `ALLOWED_ORIGIN` are read from environment variables
  (see `template.yaml`) rather than hardcoded, so the same code deploys to
  any environment.
- Every write is validated (non-empty task text, length limit, allowed
  status values) and returns `400` on bad input instead of a raw stack trace.
- Updates and deletes use a DynamoDB `ConditionExpression` so a request
  against a missing `taskId` returns `404` instead of silently succeeding.
  `PUT` accepts either or both of `task` and `status`, so editing a task's
  text is a first-class operation, not just a status flip.
- Unexpected errors are logged server-side and return a generic `500`/`502`
  message — internal exception details are never sent to the client.
- `GET` paginates through `Scan` (`LastEvaluatedKey`) instead of assuming the
  whole table fits in one page, and results are returned oldest-first.

## Known limitation: no authentication

The API has **no authentication** — anyone with the URL can read, add, edit,
or delete tasks. That's acceptable for a personal demo/portfolio project
behind an unguessable URL, but before using this for anything real you
should add one of:

- An API Gateway **API key** + usage plan (quick, coarse-grained)
- **Amazon Cognito** or a Lambda authorizer (per-user auth, needed if
  multiple people will use the app and shouldn't see each other's tasks)
- At minimum, set `ALLOWED_ORIGIN` (see below) to your actual site origin
  instead of `*`, and consider AWS WAF for basic rate limiting/abuse
  protection.

## Deploying

### Option A: AWS SAM (recommended, reproducible)

Requires the [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
and AWS credentials configured locally.

```bash
sam build
sam deploy --guided
```

`sam deploy --guided` walks you through stack name, region, and the
`AllowedOrigin` parameter, and remembers your answers in `samconfig.toml`
(gitignored) for future deploys. When it finishes, note the `ApiUrl` and
`WebsiteUrl` outputs:

```bash
aws cloudformation describe-stacks --stack-name <your-stack-name> \
  --query "Stacks[0].Outputs"
```

Put the `ApiUrl` value into [config.js](config.js):

```js
const APP_CONFIG = {
  API_BASE_URL: "https://<api-id>.execute-api.<region>.amazonaws.com/prod",
};
```

Then upload the frontend to the bucket the stack created:

```bash
aws s3 sync . s3://<website-bucket-name> \
  --exclude "*" --include "index.html" --include "style.css" \
  --include "config.js" --include "script.js" --include "Web-Logo.png"
```

Open the `WebsiteUrl` output in a browser.

### Option B: Manual console setup

1. **DynamoDB** – create a table (any name) with partition key `taskId` (String).
2. **Lambda** – create a Python 3.12 function, paste in `lambda_function.py`,
   and set environment variables `TABLE_NAME` (your table's name) and
   `ALLOWED_ORIGIN` (your site's origin, or `*` for local testing). Attach a
   role with `dynamodb:GetItem/PutItem/UpdateItem/DeleteItem/Scan` on that
   table.
3. **API Gateway** – create a REST API with a single resource (`/`) that
   proxies `GET`, `POST`, `PUT`, `DELETE`, and `OPTIONS` to the Lambda
   function, then deploy a stage (e.g. `prod`).
4. **S3** – create a bucket, enable static website hosting, and upload
   `index.html`, `style.css`, `config.js`, `script.js`, and `Web-Logo.png`.
5. Edit `config.js` with the API Gateway invoke URL from step 3 and re-upload it.

## Running the frontend locally

The frontend needs no build step or backend running locally — it just needs
to be served over `http://`/`https://` (not `file://`, since some browsers
restrict fetch from local files) and pointed at a deployed API:

```bash
python -m http.server 8000
# open http://localhost:8000
```

## Running the backend tests

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
pytest
```

Tests mock DynamoDB with [`moto`](https://github.com/getmoto/moto), so no
AWS account or credentials are needed to run them.

## API reference

Base URL is whatever `config.js` / API Gateway gives you.

| Method | Body | Response | Notes |
|---|---|---|---|
| `GET`  | — | `200` array of tasks | Sorted oldest-first |
| `POST` | `{"task": "..."}` | `201` created task | `400` if `task` is missing/empty/too long |
| `PUT`  | `{"taskId": "...", "task"?: "...", "status"?: "pending"\|"done"}` | `200` updated task | `400` invalid input, `404` unknown `taskId` |
| `DELETE` | `{"taskId": "..."}` | `200 {"deleted": taskId}` | `404` unknown `taskId` |

## Roadmap / possible next steps

- Add authentication (Cognito or an API key) so this is safe to expose publicly
- Move the frontend behind CloudFront + HTTPS instead of the plain S3 website endpoint
- Add due dates / priorities and a corresponding DynamoDB GSI for sorting
- Add end-to-end tests (e.g. Playwright) against a deployed stack in CI
