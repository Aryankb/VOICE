"""
DynamoDB database client with async operations
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import aioboto3
from botocore.exceptions import ClientError
from botocore.config import Config as BotoConfig
from config import settings
from exceptions import DatabaseException

logger = logging.getLogger(__name__)


class DynamoDBClient:
    """
    Async DynamoDB client with connection pooling and retry logic
    """

    def __init__(self):
        self.region = settings.aws_region
        self.session = None
        self._initialized = False

        # Boto3 config with retry logic
        self.boto_config = BotoConfig(
            region_name=self.region,
            retries={
                'max_attempts': 3,
                'mode': 'adaptive'
            },
            max_pool_connections=50
        )

    async def _ensure_initialized(self):
        """Ensure the session is initialized"""
        if not self._initialized:
            # Create session with credentials if provided
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                self.session = aioboto3.Session(
                    aws_access_key_id=settings.aws_access_key_id,
                    aws_secret_access_key=settings.aws_secret_access_key,
                    region_name=self.region
                )
            else:
                # Use default credential chain
                self.session = aioboto3.Session(region_name=self.region)

            self._initialized = True

    async def get_item(
        self,
        table_name: str,
        key: Dict[str, Any],
        consistent_read: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single item from DynamoDB

        Args:
            table_name: Name of the table
            key: Primary key of the item
            consistent_read: Whether to use strongly consistent read

        Returns:
            Item dict or None if not found
        """
        await self._ensure_initialized()

        try:
            async with self.session.resource('dynamodb', config=self.boto_config) as dynamodb:
                table = await dynamodb.Table(table_name)
                response = await table.get_item(
                    Key=key,
                    ConsistentRead=consistent_read
                )

                item = response.get('Item')
                if item:
                    logger.debug(f"Retrieved item from {table_name}: {key}")
                return item

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"DynamoDB GetItem error ({error_code}): {e}")
            raise DatabaseException(f"Failed to get item: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in get_item: {e}")
            raise DatabaseException(f"Unexpected error: {e}")

    async def put_item(
        self,
        table_name: str,
        item: Dict[str, Any],
        condition_expression: Optional[str] = None
    ) -> bool:
        """
        Put an item into DynamoDB

        Args:
            table_name: Name of the table
            item: Item to insert
            condition_expression: Optional condition for the put

        Returns:
            True if successful
        """
        await self._ensure_initialized()

        try:
            async with self.session.resource('dynamodb', config=self.boto_config) as dynamodb:
                table = await dynamodb.Table(table_name)

                kwargs = {'Item': item}
                if condition_expression:
                    kwargs['ConditionExpression'] = condition_expression

                await table.put_item(**kwargs)
                logger.debug(f"Put item into {table_name}")
                return True

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ConditionalCheckFailedException':
                logger.warning(f"Condition failed for put_item in {table_name}")
                return False
            logger.error(f"DynamoDB PutItem error ({error_code}): {e}")
            raise DatabaseException(f"Failed to put item: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in put_item: {e}")
            raise DatabaseException(f"Unexpected error: {e}")

    async def update_item(
        self,
        table_name: str,
        key: Dict[str, Any],
        updates: Dict[str, Any],
        condition_expression: Optional[str] = None
    ) -> bool:
        """
        Update an item in DynamoDB

        Args:
            table_name: Name of the table
            key: Primary key of the item
            updates: Dictionary of attribute updates {attr_name: new_value}
            condition_expression: Optional condition for the update

        Returns:
            True if successful
        """
        await self._ensure_initialized()

        try:
            from decimal import Decimal

            # Build update expression
            update_expr_parts = []
            expr_attr_names = {}
            expr_attr_values = {}

            for i, (attr_name, value) in enumerate(updates.items()):
                placeholder_name = f"#attr{i}"
                placeholder_value = f":val{i}"
                update_expr_parts.append(f"{placeholder_name} = {placeholder_value}")
                expr_attr_names[placeholder_name] = attr_name

                # Convert floats to Decimal for DynamoDB
                if isinstance(value, float):
                    expr_attr_values[placeholder_value] = Decimal(str(value))
                elif isinstance(value, list):
                    # Convert floats in lists to Decimal
                    expr_attr_values[placeholder_value] = self._convert_floats_to_decimal(value)
                elif isinstance(value, dict):
                    # Convert floats in dicts to Decimal
                    expr_attr_values[placeholder_value] = self._convert_floats_to_decimal(value)
                else:
                    expr_attr_values[placeholder_value] = value

            update_expression = "SET " + ", ".join(update_expr_parts)

            async with self.session.resource('dynamodb', config=self.boto_config) as dynamodb:
                table = await dynamodb.Table(table_name)

                kwargs = {
                    'Key': key,
                    'UpdateExpression': update_expression,
                    'ExpressionAttributeNames': expr_attr_names,
                    'ExpressionAttributeValues': expr_attr_values
                }

                if condition_expression:
                    kwargs['ConditionExpression'] = condition_expression

                await table.update_item(**kwargs)
                logger.debug(f"Updated item in {table_name}: {key}")
                return True

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ConditionalCheckFailedException':
                logger.warning(f"Condition failed for update_item in {table_name}")
                return False
            logger.error(f"DynamoDB UpdateItem error ({error_code}): {e}")
            raise DatabaseException(f"Failed to update item: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in update_item: {e}")
            raise DatabaseException(f"Unexpected error: {e}")

    def _convert_floats_to_decimal(self, obj):
        """Recursively convert floats to Decimal in nested structures"""
        from decimal import Decimal

        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: self._convert_floats_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_floats_to_decimal(item) for item in obj]
        else:
            return obj

    async def query(
        self,
        table_name: str,
        key_condition_expression: str,
        expression_attribute_values: Dict[str, Any],
        index_name: Optional[str] = None,
        limit: Optional[int] = None,
        scan_forward: bool = False,
        expression_attribute_names: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Query items from DynamoDB

        Args:
            table_name: Name of the table
            key_condition_expression: Key condition (e.g., "agent_id = :agent_id")
            expression_attribute_values: Values for the expression
            index_name: Optional GSI name
            limit: Maximum number of items to return
            scan_forward: Query order (True=ascending, False=descending)
            expression_attribute_names: Optional attribute name mappings

        Returns:
            List of items
        """
        await self._ensure_initialized()

        try:
            async with self.session.resource('dynamodb', config=self.boto_config) as dynamodb:
                table = await dynamodb.Table(table_name)

                kwargs = {
                    'KeyConditionExpression': key_condition_expression,
                    'ExpressionAttributeValues': expression_attribute_values,
                    'ScanIndexForward': scan_forward
                }

                if index_name:
                    kwargs['IndexName'] = index_name

                if limit:
                    kwargs['Limit'] = limit

                if expression_attribute_names:
                    kwargs['ExpressionAttributeNames'] = expression_attribute_names

                response = await table.query(**kwargs)
                items = response.get('Items', [])

                logger.debug(f"Queried {len(items)} items from {table_name}")
                return items

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"DynamoDB Query error ({error_code}): {e}")
            raise DatabaseException(f"Failed to query: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in query: {e}")
            raise DatabaseException(f"Unexpected error: {e}")

    async def delete_item(
        self,
        table_name: str,
        key: Dict[str, Any]
    ) -> bool:
        """
        Delete an item from DynamoDB

        Args:
            table_name: Name of the table
            key: Primary key of the item

        Returns:
            True if successful
        """
        await self._ensure_initialized()

        try:
            async with self.session.resource('dynamodb', config=self.boto_config) as dynamodb:
                table = await dynamodb.Table(table_name)
                await table.delete_item(Key=key)
                logger.debug(f"Deleted item from {table_name}: {key}")
                return True

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"DynamoDB DeleteItem error ({error_code}): {e}")
            raise DatabaseException(f"Failed to delete item: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in delete_item: {e}")
            raise DatabaseException(f"Unexpected error: {e}")

    async def batch_write_items(
        self,
        table_name: str,
        items: List[Dict[str, Any]]
    ) -> bool:
        """
        Batch write items to DynamoDB

        Args:
            table_name: Name of the table
            items: List of items to write

        Returns:
            True if successful
        """
        await self._ensure_initialized()

        try:
            async with self.session.resource('dynamodb', config=self.boto_config) as dynamodb:
                table = await dynamodb.Table(table_name)

                # DynamoDB batch_writer handles chunking into batches of 25
                async with table.batch_writer() as batch:
                    for item in items:
                        await batch.put_item(Item=item)

                logger.debug(f"Batch wrote {len(items)} items to {table_name}")
                return True

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"DynamoDB BatchWrite error ({error_code}): {e}")
            raise DatabaseException(f"Failed to batch write: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in batch_write_items: {e}")
            raise DatabaseException(f"Unexpected error: {e}")


# Global database client instance
db_client = DynamoDBClient()
