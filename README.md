# AWS FIFO Queue Creator for Messaging Applications

A simple tool to quickly create AWS SQS FIFO queues with associated Lambda functions for processing and sending messages.

## Features

- One-command setup of a complete AWS SQS FIFO queue system
- Creates two Lambda functions:
  - A sender function to enqueue messages
  - A processor function to handle messages
- Automatically configures IAM roles and permissions
- Perfect for building:
  - Messaging applications
  - Phone call handling systems
  - Event-driven architectures
  - Task queues with ordered processing

## Why FIFO Queues?

FIFO (First-In-First-Out) queues guarantee that messages are processed exactly once and in the order they are sent. This is critical for applications where message order matters, such as:

- Tracking phone call status updates (ringing → answered → completed)
- Processing messages in a conversation

## Usage

```python
python create_fifo_q.py
```

By default, the script creates a queue with the name "rohowef_f_q.fifo" and associated resources. You can modify the base name in the script.

## Example: Sending Messages

```python
import boto3
import json

lambda_client = boto3.client('lambda')

# Example payload
payload = {
    'message': {
        'type': 'call_status_update',
        'call_id': '12345',
        'status': 'ringing',
        'timestamp': '2025-01-01T12:00:00Z'
    },
    'deduplicationId': '12345-ringing-2025-01-01T12:00:00Z',  # Optional
    'groupId': '12345'  # Optional
}

response = lambda_client.invoke(
    FunctionName='your_queue_name_sender',
    InvocationType='RequestResponse',
    Payload=json.dumps(payload)
)
```

## Requirements

- Python 3.x
- AWS account with appropriate permissions
- Boto3 library

## License

MIT 