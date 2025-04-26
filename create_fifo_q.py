#!/usr/bin/env python3
import boto3
import json
import argparse
import time
import zipfile
import os
import tempfile

def create_fifo_queue_and_lambdas(base_name):
    """
    Creates an SQS FIFO queue and two Lambda functions:
    1. A processor Lambda that consumes messages from the queue
    2. A sender Lambda that can be triggered to send messages to the queue
    
    Args:
        base_name (str): Base name for the resources (e.g., 'roho_test_q')
    """
    # Initialize AWS clients
    sqs = boto3.client('sqs')
    iam = boto3.client('iam')
    lambda_client = boto3.client('lambda')
    
    # Set resource names
    queue_name = f"{base_name}.fifo"
    processor_lambda_name = f"{base_name}_processor"
    sender_lambda_name = f"{base_name}_sender"
    processor_role_name = f"{base_name}_processor_role"
    sender_role_name = f"{base_name}_sender_role"
    
    print(f"Creating resources with base name: {base_name}")
    
    # Step 1: Create FIFO queue
    try:
        print(f"Creating FIFO queue: {queue_name}")
        queue_response = sqs.create_queue(
            QueueName=queue_name,
            Attributes={
                'FifoQueue': 'true',
                'ContentBasedDeduplication': 'false',  # Disabled content-based deduplication
                'VisibilityTimeout': '300',  # 5 minutes
                'ReceiveMessageWaitTimeSeconds': '20'  # Long polling
            }
        )
        queue_url = queue_response['QueueUrl']
        queue_arn = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['QueueArn']
        )['Attributes']['QueueArn']
        print(f"Queue created: {queue_url}")
    except Exception as e:
        print(f"Error creating queue: {e}")
        return
    
    # Step 2: Create IAM role for processor Lambda
    try:
        print(f"Creating IAM role for processor: {processor_role_name}")
        # Create trust relationship policy
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        # Check if role already exists
        try:
            processor_role_response = iam.get_role(RoleName=processor_role_name)
            processor_role_arn = processor_role_response['Role']['Arn']
            print(f"Using existing IAM role for processor: {processor_role_arn}")
        except iam.exceptions.NoSuchEntityException:
            # Create IAM role
            processor_role_response = iam.create_role(
                RoleName=processor_role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description=f"Role for {processor_lambda_name} Lambda function"
            )
            processor_role_arn = processor_role_response['Role']['Arn']
            
            # Attach policies for SQS, DynamoDB, and Lambda permissions
            iam.attach_role_policy(
                RoleName=processor_role_name,
                PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole'
            )
            iam.attach_role_policy(
                RoleName=processor_role_name,
                PolicyArn='arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess'
            )
            iam.attach_role_policy(
                RoleName=processor_role_name,
                PolicyArn='arn:aws:iam::aws:policy/AWSLambdaExecute'
            )
            
            print(f"IAM role created for processor: {processor_role_arn}")
        
        # Wait for role to propagate
        print("Waiting for processor IAM role to propagate...")
        time.sleep(10)
    except Exception as e:
        print(f"Error creating processor IAM role: {e}")
        return
    
    # Step 3: Create IAM role for sender Lambda
    try:
        print(f"Creating IAM role for sender: {sender_role_name}")
        
        # Check if role already exists
        try:
            sender_role_response = iam.get_role(RoleName=sender_role_name)
            sender_role_arn = sender_role_response['Role']['Arn']
            print(f"Using existing IAM role for sender: {sender_role_arn}")
        except iam.exceptions.NoSuchEntityException:
            # Create IAM role with same trust policy
            sender_role_response = iam.create_role(
                RoleName=sender_role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description=f"Role for {sender_lambda_name} Lambda function"
            )
            sender_role_arn = sender_role_response['Role']['Arn']
            
            # Attach policies for SQS and Lambda permissions (just needs to send messages)
            iam.attach_role_policy(
                RoleName=sender_role_name,
                PolicyArn='arn:aws:iam::aws:policy/AmazonSQSFullAccess'
            )
            iam.attach_role_policy(
                RoleName=sender_role_name,
                PolicyArn='arn:aws:iam::aws:policy/AWSLambdaExecute'
            )
            
            print(f"IAM role created for sender: {sender_role_arn}")
        
        # Wait for role to propagate
        print("Waiting for sender IAM role to propagate...")
        time.sleep(10)
    except Exception as e:
        print(f"Error creating sender IAM role: {e}")
        return
    
    # Step 4: Create processor Lambda function
    try:
        print(f"Creating processor Lambda function: {processor_lambda_name}")
        
        # Create a simple Lambda function handler for processor
        processor_lambda_code = """
import json
import uuid

def lambda_handler(event, context):
    print('Received event:', json.dumps(event))
    
    for record in event['Records']:
        # Process SQS message
        print("SQS Message ID:", record['messageId'])
        payload = record['body']
        print("Message Body:", payload)
        
        # Your processing logic here
        # For example, you could parse the message and write to DynamoDB
        
    return {
        'statusCode': 200,
        'body': json.dumps('Message processed successfully!')
    }
"""
        
        # Create a temporary deployment package
        temp_dir = tempfile.gettempdir()
        lambda_file_path = os.path.join(temp_dir, 'lambda_function.py')
        zip_file_path = os.path.join(temp_dir, 'lambda_function.zip')
        
        with open(lambda_file_path, 'w') as f:
            f.write(processor_lambda_code)
        
        with zipfile.ZipFile(zip_file_path, 'w') as z:
            z.write(lambda_file_path, 'lambda_function.py')
        
        with open(zip_file_path, 'rb') as f:
            processor_lambda_package = f.read()
        
        # Check if function already exists
        try:
            function_response = lambda_client.get_function(FunctionName=processor_lambda_name)
            # Function exists, update its code
            processor_lambda_response = lambda_client.update_function_code(
                FunctionName=processor_lambda_name,
                ZipFile=processor_lambda_package
            )
            processor_lambda_arn = processor_lambda_response['FunctionArn']
            print(f"Updated processor Lambda function: {processor_lambda_arn}")
        except lambda_client.exceptions.ResourceNotFoundException:
            # Function doesn't exist, create it
            processor_lambda_response = lambda_client.create_function(
                FunctionName=processor_lambda_name,
                Runtime='python3.10',
                Role=processor_role_arn,
                Handler='lambda_function.lambda_handler',
                Code={'ZipFile': processor_lambda_package},
                Description=f'Lambda processor for {queue_name} FIFO queue',
                Timeout=30,
                MemorySize=128,
                Publish=True
            )
            processor_lambda_arn = processor_lambda_response['FunctionArn']
            print(f"Processor Lambda function created: {processor_lambda_arn}")
        
        # Clean up temporary files
        os.remove(lambda_file_path)
        os.remove(zip_file_path)
        
    except Exception as e:
        print(f"Error creating processor Lambda function: {e}")
        return
    
    # Step 5: Create sender Lambda function
    try:
        print(f"Creating sender Lambda function: {sender_lambda_name}")
        
        # Create Lambda function handler for sender
        sender_lambda_code = f"""
import json
import boto3
import uuid

# Initialize SQS client
sqs = boto3.client('sqs')

# Queue details
QUEUE_URL = '{queue_url}'

def lambda_handler(event, context):
    try:
        # Extract message details from event
        if 'body' in event:
            # If coming from API Gateway
            try:
                body = json.loads(event['body'])
            except:
                body = event['body']
        else:
            # If invoked directly
            body = event
        
        # Get message content - with fallbacks for various input formats
        message_content = body.get('message', body.get('Message', body))
        
        # Generate or use provided message ID for deduplication
        dedup_id = body.get('deduplicationId', str(uuid.uuid4()))
        
        # Get message group ID (required for FIFO) - default to a fixed value if not provided
        group_id = body.get('groupId', 'default-group')
        
        print(f"Sending message to queue: {{QUEUE_URL}}")
        print(f"Message content: {{json.dumps(message_content, default=str)}}")
        print(f"Deduplication ID: {{dedup_id}}")
        print(f"Group ID: {{group_id}}")
        
        # Send message to SQS FIFO queue
        response = sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(message_content, default=str),
            MessageDeduplicationId=dedup_id,
            MessageGroupId=group_id
        )
        
        return {{
            'statusCode': 200,
            'body': json.dumps({{
                'message': 'Message sent successfully',
                'messageId': response.get('MessageId'),
                'sequenceNumber': response.get('SequenceNumber')
            }})
        }}
    except Exception as e:
        print(f"Error sending message: {{str(e)}}")
        return {{
            'statusCode': 500,
            'body': json.dumps({{
                'error': str(e)
            }})
        }}
"""
        
        # Create a temporary deployment package
        temp_dir = tempfile.gettempdir()
        lambda_file_path = os.path.join(temp_dir, 'lambda_function.py')
        zip_file_path = os.path.join(temp_dir, 'lambda_function.zip')
        
        with open(lambda_file_path, 'w') as f:
            f.write(sender_lambda_code)
        
        with zipfile.ZipFile(zip_file_path, 'w') as z:
            z.write(lambda_file_path, 'lambda_function.py')
        
        with open(zip_file_path, 'rb') as f:
            sender_lambda_package = f.read()
        
        # Check if function already exists
        try:
            function_response = lambda_client.get_function(FunctionName=sender_lambda_name)
            # Function exists, update its code
            sender_lambda_response = lambda_client.update_function_code(
                FunctionName=sender_lambda_name,
                ZipFile=sender_lambda_package
            )
            sender_lambda_arn = sender_lambda_response['FunctionArn']
            print(f"Updated sender Lambda function: {sender_lambda_arn}")
        except lambda_client.exceptions.ResourceNotFoundException:
            # Function doesn't exist, create it
            sender_lambda_response = lambda_client.create_function(
                FunctionName=sender_lambda_name,
                Runtime='python3.10',
                Role=sender_role_arn,
                Handler='lambda_function.lambda_handler',
                Code={'ZipFile': sender_lambda_package},
                Description=f'Lambda sender for {queue_name} FIFO queue',
                Timeout=30,
                MemorySize=128,
                Publish=True
            )
            sender_lambda_arn = sender_lambda_response['FunctionArn']
            print(f"Sender Lambda function created: {sender_lambda_arn}")
        
        # Clean up temporary files
        os.remove(lambda_file_path)
        os.remove(zip_file_path)
        
    except Exception as e:
        print(f"Error creating sender Lambda function: {e}")
        return
    
    # Step 6: Connect SQS and processor Lambda - Create event source mapping
    try:
        print(f"Setting up SQS trigger for processor Lambda...")
        lambda_client.create_event_source_mapping(
            EventSourceArn=queue_arn,
            FunctionName=processor_lambda_name,
            Enabled=True,
            BatchSize=1  # Process one message at a time
        )
        print(f"SQS trigger configured successfully")
    except Exception as e:
        print(f"Error setting up SQS trigger: {e}")
        return
    
    print("\nSetup complete!")
    print(f"FIFO Queue URL: {queue_url}")
    print(f"Processor Lambda: {processor_lambda_name}")
    print(f"Sender Lambda: {sender_lambda_name}")
    
    print("\nTo invoke the sender Lambda to send a message:")
    print(f"""
import boto3
import json

lambda_client = boto3.client('lambda')

# Example payload
payload = {{
    'message': {{
        'type': 'call_status_update',
        'call_id': '12345',
        'status': 'ringing',
        'timestamp': '2025-01-01T12:00:00Z'
    }},
    'deduplicationId': '12345-ringing-2025-01-01T12:00:00Z',  # Optional - will be generated if not provided
    'groupId': '12345'  # Optional - will use 'default-group' if not provided
}}

response = lambda_client.invoke(
    FunctionName='{sender_lambda_name}',
    InvocationType='RequestResponse',  # Use 'Event' for async
    Payload=json.dumps(payload)
)

if response.get('StatusCode') == 200:
    result = json.loads(response['Payload'].read())
    print("Message sent successfully!")
    print(result)
else:
    print("Error sending message:", response)
    """)
    
    return {
        "queue_name": queue_name,
        "queue_arn": queue_arn,
        "queue_url": queue_url,
        "processor_lambda_name": processor_lambda_name,
        "processor_lambda_arn": processor_lambda_arn,
        "sender_lambda_name": sender_lambda_name,
        "sender_lambda_arn": sender_lambda_arn
    }

if __name__ == "__main__":
    name = "rohowef_f_q"
    
    response = create_fifo_queue_and_lambdas(name)
    print(response)