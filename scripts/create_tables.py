"""
Script to create DynamoDB tables for the Twilio Voice AI Assistant

Usage:
    python scripts/create_tables.py
"""

import boto3
import sys
import os
from botocore.exceptions import ClientError

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings


def create_agents_table(dynamodb_client):
    """Create Agents table with StatusIndex GSI"""
    table_name = settings.dynamodb_table_agents

    try:
        table = dynamodb_client.create_table(
            TableName=table_name,
            KeySchema=[
                {'AttributeName': 'agent_id', 'KeyType': 'HASH'}  # Partition key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'agent_id', 'AttributeType': 'S'},
                {'AttributeName': 'status', 'AttributeType': 'S'},
                {'AttributeName': 'created_at', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'StatusIndex',
                    'KeySchema': [
                        {'AttributeName': 'status', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                }
            ],
            BillingMode='PAY_PER_REQUEST',  # On-demand pricing
            SSESpecification={
                'Enabled': True,
                'SSEType': 'KMS'  # Server-side encryption
            },
            Tags=[
                {'Key': 'Project', 'Value': 'VoiceAssistant'},
                {'Key': 'Environment', 'Value': 'Production'}
            ]
        )

        print(f"✓ Creating table: {table_name}")
        table.wait_until_exists()
        print(f"✓ Table {table_name} created successfully!")
        return True

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceInUseException':
            print(f"⚠ Table {table_name} already exists")
            return True
        else:
            print(f"✗ Error creating {table_name}: {e}")
            return False


def create_calls_table(dynamodb_client):
    """Create Calls table with 3 GSIs"""
    table_name = settings.dynamodb_table_calls

    try:
        table = dynamodb_client.create_table(
            TableName=table_name,
            KeySchema=[
                {'AttributeName': 'call_sid', 'KeyType': 'HASH'}  # Partition key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'call_sid', 'AttributeType': 'S'},
                {'AttributeName': 'agent_id', 'AttributeType': 'S'},
                {'AttributeName': 'recipient_phone', 'AttributeType': 'S'},
                {'AttributeName': 'started_at', 'AttributeType': 'S'},
                {'AttributeName': 'status', 'AttributeType': 'S'},
                {'AttributeName': 'agent_recipient_key', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'AgentRecipientIndex',
                    'KeySchema': [
                        {'AttributeName': 'agent_id', 'KeyType': 'HASH'},
                        {'AttributeName': 'agent_recipient_key', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                },
                {
                    'IndexName': 'RecipientIndex',
                    'KeySchema': [
                        {'AttributeName': 'recipient_phone', 'KeyType': 'HASH'},
                        {'AttributeName': 'started_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                },
                {
                    'IndexName': 'StatusIndex',
                    'KeySchema': [
                        {'AttributeName': 'status', 'KeyType': 'HASH'},
                        {'AttributeName': 'started_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                }
            ],
            BillingMode='PAY_PER_REQUEST',
            SSESpecification={
                'Enabled': True,
                'SSEType': 'KMS'
            },
            Tags=[
                {'Key': 'Project', 'Value': 'VoiceAssistant'},
                {'Key': 'Environment', 'Value': 'Production'}
            ]
        )

        print(f"✓ Creating table: {table_name}")
        table.wait_until_exists()
        print(f"✓ Table {table_name} created successfully!")
        return True

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceInUseException':
            print(f"⚠ Table {table_name} already exists")
            return True
        else:
            print(f"✗ Error creating {table_name}: {e}")
            return False


def create_phone_numbers_table(dynamodb_client):
    """Create PhoneNumbers table"""
    table_name = settings.dynamodb_table_phone_numbers

    try:
        table = dynamodb_client.create_table(
            TableName=table_name,
            KeySchema=[
                {'AttributeName': 'phone_number', 'KeyType': 'HASH'}  # Partition key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'phone_number', 'AttributeType': 'S'},
                {'AttributeName': 'assigned_agent_id', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'AgentIndex',
                    'KeySchema': [
                        {'AttributeName': 'assigned_agent_id', 'KeyType': 'HASH'}
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                }
            ],
            BillingMode='PAY_PER_REQUEST',
            SSESpecification={
                'Enabled': True,
                'SSEType': 'KMS'
            },
            Tags=[
                {'Key': 'Project', 'Value': 'VoiceAssistant'},
                {'Key': 'Environment', 'Value': 'Production'}
            ]
        )

        print(f"✓ Creating table: {table_name}")
        table.wait_until_exists()
        print(f"✓ Table {table_name} created successfully!")
        return True

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceInUseException':
            print(f"⚠ Table {table_name} already exists")
            return True
        else:
            print(f"✗ Error creating {table_name}: {e}")
            return False


def verify_tables(dynamodb_client):
    """Verify all tables are created and active"""
    tables_to_verify = [
        settings.dynamodb_table_agents,
        settings.dynamodb_table_calls,
        settings.dynamodb_table_phone_numbers
    ]

    print("\n--- Verifying Tables ---")
    all_active = True

    for table_name in tables_to_verify:
        try:
            table = dynamodb_client.Table(table_name)
            table.load()
            status = table.table_status

            if status == 'ACTIVE':
                print(f"✓ {table_name}: {status}")
            else:
                print(f"⚠ {table_name}: {status}")
                all_active = False

        except ClientError as e:
            print(f"✗ {table_name}: NOT FOUND")
            all_active = False

    return all_active


def main():
    """Main function to create all tables"""
    print("=" * 60)
    print("DynamoDB Table Creation Script")
    print("=" * 60)
    print(f"Region: {settings.aws_region}")
    print(f"Agent Table: {settings.dynamodb_table_agents}")
    print(f"Calls Table: {settings.dynamodb_table_calls}")
    print(f"Phone Numbers Table: {settings.dynamodb_table_phone_numbers}")
    print("=" * 60)

    # Create boto3 client
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        dynamodb = boto3.resource(
            'dynamodb',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key
        )
    else:
        dynamodb = boto3.resource('dynamodb', region_name=settings.aws_region)

    print("\n--- Creating Tables ---")

    # Create tables
    success_count = 0
    if create_agents_table(dynamodb):
        success_count += 1

    if create_calls_table(dynamodb):
        success_count += 1

    if create_phone_numbers_table(dynamodb):
        success_count += 1

    # Verify tables
    if verify_tables(dynamodb):
        print("\n" + "=" * 60)
        print("✓ All tables created and active!")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("⚠ Some tables are not active. Please check AWS Console.")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
