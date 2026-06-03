# Oblak CDK CLI

Command-line tool for deploying and managing Python functions on the Oblak serverless platform.

## Installation

```bash
cd cdk-cli
pip install -e .
```

After installation, the `cdk` command is available globally.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OBLAK_SERVER_URL` | `http://localhost:8000` | Base URL of the Oblak API server |

## Usage

### Login

```bash
cdk login
```

Prompts for your API token (hidden input), validates it via `GET /auth/me`, and stores it in `~/.cdk/config.json` with permissions `600`.

### Deploy a function

```bash
cdk deploy handler.py
```

Uploads the `.py` file (and `requirements.txt` from the same directory, if present) via `POST /functions`. Prints the invoke URL on success.

### List functions

```bash
cdk list
```

Displays a table of your deployed functions (id, name, status, invoke_url).

### Delete a function

```bash
cdk delete <function_id>
```

Prompts for confirmation before sending `DELETE /functions/{id}`.

## Error Handling

- Network errors print a human-readable message and exit with code 1.
- HTTP 401 responses print `Not authorized — run: cdk login`.
- Other 4xx responses print the error message from the server JSON body.
- Raw tracebacks are never shown to the user.

## Security

- The auth token is never logged or printed.
- Config file (`~/.cdk/config.json`) is created with permissions `600` (user read/write only).
- Config directory (`~/.cdk/`) is created with permissions `700`.

## Assumptions

- **Python 3.11+** is the target runtime.
- **Server API** follows the agreed contract: `GET /auth/me`, `POST /functions`, `GET /functions`, `DELETE /functions/{id}`.
- **POST /functions** response shape: `{"function_id": "uuid", "invoke_url": "http://server/run/uuid"}`.
- **GET /functions** returns a JSON array of function objects with `id` (or `function_id`), `name`, `status`, and `invoke_url` fields.
- **Multipart upload** uses field names `file` for the Python source and `requirements` for an optional requirements.txt.
- **Token storage** is a single JSON file at `~/.cdk/config.json` with key `"token"`.
