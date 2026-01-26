"""
DynamoDB client wrapper for voice.py compatibility
This provides a synchronous boto3 client interface
"""

import boto3
import logging
from config import settings

logger = logging.getLogger(__name__)


class DynamoDBClientWrapper:
    """
    Wrapper around boto3 DynamoDB client for voice.py compatibility.
    Uses raw DynamoDB format with type descriptors ({'S': value}, {'N': value}).
    """

    def __init__(self):
        # Initialize boto3 client (not resource)
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            self.client = boto3.client(
                'dynamodb',
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key
            )
        else:
            # Use default credential chain
            self.client = boto3.client(
                'dynamodb',
                region_name=settings.aws_region
            )

        logger.info("DynamoDB client initialized for voice.py")

    def get_item(self, TableName: str, Key: dict):
        """Get item from DynamoDB table"""
        try:
            return self.client.get_item(TableName=TableName, Key=Key)
        except Exception as e:
            logger.error(f"Error getting item from {TableName}: {e}")
            raise

    def put_item(self, TableName: str, Item: dict, **kwargs):
        """Put item into DynamoDB table"""
        try:
            return self.client.put_item(TableName=TableName, Item=Item, **kwargs)
        except Exception as e:
            logger.error(f"Error putting item to {TableName}: {e}")
            raise

    def query(self, TableName: str, **kwargs):
        """Query DynamoDB table"""
        try:
            return self.client.query(TableName=TableName, **kwargs)
        except Exception as e:
            logger.error(f"Error querying {TableName}: {e}")
            raise

    def update_item(self, TableName: str, Key: dict, UpdateExpression: str,
                    ExpressionAttributeValues: dict, **kwargs):
        """Update item in DynamoDB table"""
        try:
            return self.client.update_item(
                TableName=TableName,
                Key=Key,
                UpdateExpression=UpdateExpression,
                ExpressionAttributeValues=ExpressionAttributeValues,
                **kwargs
            )
        except Exception as e:
            logger.error(f"Error updating item in {TableName}: {e}")
            raise

    def delete_item(self, TableName: str, Key: dict, **kwargs):
        """Delete item from DynamoDB table"""
        try:
            return self.client.delete_item(TableName=TableName, Key=Key, **kwargs)
        except Exception as e:
            logger.error(f"Error deleting item from {TableName}: {e}")
            raise


# Global client instance for voice.py
db_client = DynamoDBClientWrapper()
