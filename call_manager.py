"""
Call manager for handling call lifecycle and conversation history (SIGMOYD-BACKEND schema)
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from tools.dynamo import db_client
from models import CallRecord, ConversationMessage
from config import settings
from exceptions import CallRecordNotFoundException

logger = logging.getLogger(__name__)


def fetch_past_conversations(
    agent_id: str,
    recipient_phone: str,
    limit: int = 5
) -> List[CallRecord]:
    """
    Fetch past conversations for an agent-recipient pair (SIGMOYD-BACKEND schema - SYNC)

    Note: Uses agent_id partition key query and filters by recipient_number.
    For production, consider adding a GSI on agent_id + recipient_number for better performance.

    Args:
        agent_id: Agent identifier
        recipient_phone: Recipient phone number
        limit: Maximum number of past calls to retrieve (default: 5)

    Returns:
        List of CallRecord objects, most recent first
    """
    try:
        # Query by agent_id (partition key)
        response = db_client.query(
            TableName=settings.dynamodb_table_calls,
            KeyConditionExpression='agent_id = :agent_id',
            ExpressionAttributeValues={
                ':agent_id': {'S': agent_id}
            },
            ScanIndexForward=False,  # Descending order (most recent first)
            Limit=limit * 3  # Get more since we filter by recipient
        )

        items = response.get('Items', [])

        # Filter by recipient_number
        filtered_items = [
            item for item in items
            if item.get('recipient_number', {}).get('S', '') == recipient_phone
        ][:limit]

        # Parse into CallRecord objects
        past_calls = []
        for item in filtered_items:
            try:
                # Extract from DynamoDB format
                call_sid = item.get('call_sid', {}).get('S', '')
                agent_id_val = item.get('agent_id', {}).get('S', '')
                recipient_number = item.get('recipient_number', {}).get('S', '')
                from_number = item.get('from_number', {}).get('S', '')
                status = item.get('status', {}).get('S', 'unknown')
                timestamp_start = item.get('timestamp_start', {}).get('S', '')
                timestamp_end = item.get('timestamp_end', {}).get('S')
                duration = item.get('duration', {}).get('N')

                # Parse conversation_history if exists
                conversation_history = []
                if 'conversation_history' in item:
                    conv_list = item['conversation_history'].get('L', [])
                    for msg in conv_list:
                        msg_dict = {}
                        msg_map = msg.get('M', {})
                        for key, val in msg_map.items():
                            if 'S' in val:
                                msg_dict[key] = val['S']
                            elif 'N' in val:
                                msg_dict[key] = float(val['N'])
                        if msg_dict:
                            conversation_history.append(ConversationMessage(**msg_dict))

                # Parse data_collected if exists
                data_collected = {}
                if 'data_collected' in item:
                    data_map = item['data_collected'].get('M', {})
                    for key, val in data_map.items():
                        if 'S' in val:
                            data_collected[key] = val['S']
                        elif 'N' in val:
                            data_collected[key] = float(val['N'])

                call_record = CallRecord(
                    call_sid=call_sid,
                    agent_id=agent_id_val,
                    recipient_phone=recipient_number,
                    caller_phone=from_number,
                    status=status,
                    started_at=timestamp_start,
                    ended_at=timestamp_end,
                    duration_seconds=int(duration) if duration else None,
                    conversation_history=conversation_history,
                    data_collected=data_collected
                )
                past_calls.append(call_record)
            except Exception as parse_error:
                logger.warning(f"Failed to parse call record: {parse_error}")
                continue

        logger.info(
            f"Fetched {len(past_calls)} past conversations for "
            f"agent {agent_id} and recipient {recipient_phone}"
        )

        return past_calls

    except Exception as e:
        logger.error(
            f"Error fetching past conversations for agent {agent_id}, "
            f"recipient {recipient_phone}: {e}"
        )
        # Return empty list on error (graceful degradation)
        return []


def create_call_record(
    call_sid: str,
    agent_id: str,
    recipient_phone: str,
    caller_phone: str,
    status: str = "initiated"
) -> CallRecord:
    """
    Create initial call record in DynamoDB (SIGMOYD-BACKEND schema - SYNC)

    Args:
        call_sid: Twilio call SID
        agent_id: Agent identifier
        recipient_phone: Phone number being called
        caller_phone: Phone number calling from
        status: Initial call status

    Returns:
        CallRecord object
    """
    try:
        call_record = CallRecord(
            call_sid=call_sid,
            agent_id=agent_id,
            recipient_phone=recipient_phone,
            caller_phone=caller_phone,
            status=status,
            started_at=datetime.now().isoformat()
        )

        # Convert to SIGMOYD schema with type descriptors
        item = {
            'agent_id': {'S': agent_id},  # Partition key
            'call_sid': {'S': call_sid},  # Sort key
            'recipient_number': {'S': recipient_phone},
            'from_number': {'S': caller_phone},
            'status': {'S': status},
            'duration': {'N': '0'},
            'timestamp_start': {'S': call_record.started_at},
            'conversation_history': {'L': []},
            'data_collected': {'M': {}}
        }

        # Save to DynamoDB
        db_client.put_item(
            TableName=settings.dynamodb_table_calls,
            Item=item
        )

        logger.info(f"Created call record for {call_sid}")
        return call_record

    except Exception as e:
        logger.error(f"Error creating call record for {call_sid}: {e}")
        raise


def sync_conversation_to_db(
    call_sid: str,
    conversation_history: List[ConversationMessage],
    data_collected: Optional[Dict[str, Any]] = None,
    agent_id: Optional[str] = None
) -> bool:
    """
    Sync conversation history to DynamoDB (SIGMOYD-BACKEND schema - SYNC)

    Args:
        call_sid: Twilio call SID
        conversation_history: List of conversation messages
        data_collected: Optional data collected so far
        agent_id: Agent ID (required for composite key)

    Returns:
        True if successful
    """
    try:
        if not agent_id:
            logger.error(f"Cannot sync conversation for {call_sid}: agent_id required")
            return False

        # Build update expression
        update_parts = []
        expr_attr_values = {}
        expr_attr_names = {}

        # Conversation history
        conv_list = []
        for msg in conversation_history:
            msg_dict = msg.model_dump(exclude_none=True)
            msg_map = {}
            for key, val in msg_dict.items():
                if isinstance(val, str):
                    msg_map[key] = {'S': val}
                elif isinstance(val, (int, float)):
                    msg_map[key] = {'N': str(val)}
            conv_list.append({'M': msg_map})

        update_parts.append('#ch = :ch')
        expr_attr_names['#ch'] = 'conversation_history'
        expr_attr_values[':ch'] = {'L': conv_list}

        # Status
        update_parts.append('#st = :st')
        expr_attr_names['#st'] = 'status'
        expr_attr_values[':st'] = {'S': 'in-progress'}

        # Data collected
        if data_collected:
            data_map = {}
            for key, val in data_collected.items():
                if isinstance(val, str):
                    data_map[key] = {'S': val}
                elif isinstance(val, (int, float)):
                    data_map[key] = {'N': str(val)}
                elif isinstance(val, dict):
                    # Nested dict
                    nested_map = {}
                    for nk, nv in val.items():
                        if isinstance(nv, str):
                            nested_map[nk] = {'S': nv}
                        elif isinstance(nv, (int, float)):
                            nested_map[nk] = {'N': str(nv)}
                    data_map[key] = {'M': nested_map}

            update_parts.append('#dc = :dc')
            expr_attr_names['#dc'] = 'data_collected'
            expr_attr_values[':dc'] = {'M': data_map}

        update_expression = 'SET ' + ', '.join(update_parts)

        # Update with composite key
        db_client.update_item(
            TableName=settings.dynamodb_table_calls,
            Key={
                'agent_id': {'S': agent_id},
                'call_sid': {'S': call_sid}
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )

        logger.debug(
            f"Synced conversation for {call_sid}: "
            f"{len(conversation_history)} messages"
        )

        return True

    except Exception as e:
        logger.error(f"Error syncing conversation for {call_sid}: {e}")
        # Don't raise - sync is best-effort
        return False


def finalize_call(
    call_sid: str,
    status: str,
    ended_at: str,
    duration_seconds: Optional[int] = None,
    ended_by: Optional[str] = None,
    conversation_history: Optional[List[ConversationMessage]] = None,
    call_recording_url: Optional[str] = None,
    call_recording_sid: Optional[str] = None,
    s3_recording_url: Optional[str] = None,
    data_collected: Optional[Dict[str, Any]] = None,
    answered_by: Optional[str] = None,
    agent_id: Optional[str] = None
) -> bool:
    """
    Finalize call record with all end-of-call data (SIGMOYD-BACKEND schema - SYNC)

    Args:
        call_sid: Twilio call SID
        status: Final call status
        ended_at: End timestamp
        duration_seconds: Call duration
        ended_by: Who ended the call
        conversation_history: Full conversation history
        call_recording_url: Twilio recording URL
        call_recording_sid: Twilio recording SID
        s3_recording_url: S3 recording URL
        data_collected: Data collected during call
        answered_by: Who answered the call
        agent_id: Agent ID (required for composite key)

    Returns:
        True if successful
    """
    try:
        if not agent_id:
            logger.error(f"Cannot finalize call {call_sid}: agent_id required")
            return False

        # Build update expression
        update_parts = []
        expr_attr_values = {}
        expr_attr_names = {}

        # Status
        update_parts.append('#st = :st')
        expr_attr_names['#st'] = 'status'
        expr_attr_values[':st'] = {'S': status}

        # Timestamp end
        update_parts.append('timestamp_end = :te')
        expr_attr_values[':te'] = {'S': ended_at}

        # Duration
        if duration_seconds is not None:
            update_parts.append('duration = :dur')
            expr_attr_values[':dur'] = {'N': str(duration_seconds)}

        # Ended by
        if ended_by:
            update_parts.append('ended_by = :eb')
            expr_attr_values[':eb'] = {'S': ended_by}

        # Conversation history
        if conversation_history:
            conv_list = []
            for msg in conversation_history:
                msg_dict = msg.model_dump(exclude_none=True) if isinstance(msg, ConversationMessage) else msg
                msg_map = {}
                for key, val in msg_dict.items():
                    if isinstance(val, str):
                        msg_map[key] = {'S': val}
                    elif isinstance(val, (int, float)):
                        msg_map[key] = {'N': str(val)}
                conv_list.append({'M': msg_map})

            update_parts.append('#ch = :ch')
            expr_attr_names['#ch'] = 'conversation_history'
            expr_attr_values[':ch'] = {'L': conv_list}

        # Recording URLs
        if call_recording_url:
            update_parts.append('call_recording_url = :cru')
            expr_attr_values[':cru'] = {'S': call_recording_url}

        if call_recording_sid:
            update_parts.append('call_recording_sid = :crs')
            expr_attr_values[':crs'] = {'S': call_recording_sid}

        if s3_recording_url:
            update_parts.append('s3_recording_url = :s3')
            expr_attr_values[':s3'] = {'S': s3_recording_url}

        # Data collected
        if data_collected:
            data_map = {}
            for key, val in data_collected.items():
                if isinstance(val, str):
                    data_map[key] = {'S': val}
                elif isinstance(val, (int, float)):
                    data_map[key] = {'N': str(val)}

            update_parts.append('#dc = :dc')
            expr_attr_names['#dc'] = 'data_collected'
            expr_attr_values[':dc'] = {'M': data_map}

        # Answered by
        if answered_by:
            update_parts.append('answered_by = :ab')
            expr_attr_values[':ab'] = {'S': answered_by}

        update_expression = 'SET ' + ', '.join(update_parts)

        # Update with composite key
        db_client.update_item(
            TableName=settings.dynamodb_table_calls,
            Key={
                'agent_id': {'S': agent_id},
                'call_sid': {'S': call_sid}
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expr_attr_names if expr_attr_names else None,
            ExpressionAttributeValues=expr_attr_values
        )

        logger.info(
            f"Finalized call {call_sid}: status={status}, "
            f"duration={duration_seconds}s, ended_by={ended_by}"
        )

        return True

    except Exception as e:
        logger.error(f"Error finalizing call {call_sid}: {e}")
        raise


def get_call_record(call_sid: str, agent_id: Optional[str] = None) -> CallRecord:
    """
    Get call record from DynamoDB (SIGMOYD-BACKEND schema - SYNC)

    Args:
        call_sid: Twilio call SID
        agent_id: Agent ID (required for composite key)

    Returns:
        CallRecord object

    Raises:
        CallRecordNotFoundException: If call not found
    """
    try:
        if not agent_id:
            logger.error(f"Cannot get call record {call_sid}: agent_id required")
            raise CallRecordNotFoundException(f"Call {call_sid} requires agent_id")

        response = db_client.get_item(
            TableName=settings.dynamodb_table_calls,
            Key={
                'agent_id': {'S': agent_id},
                'call_sid': {'S': call_sid}
            }
        )

        item = response.get('Item')
        if not item:
            raise CallRecordNotFoundException(f"Call {call_sid} not found")

        # Parse from DynamoDB format
        call_record = CallRecord(
            call_sid=item.get('call_sid', {}).get('S', ''),
            agent_id=item.get('agent_id', {}).get('S', ''),
            recipient_phone=item.get('recipient_number', {}).get('S', ''),
            caller_phone=item.get('from_number', {}).get('S', ''),
            status=item.get('status', {}).get('S', 'unknown'),
            started_at=item.get('timestamp_start', {}).get('S', ''),
            ended_at=item.get('timestamp_end', {}).get('S'),
            duration_seconds=int(item.get('duration', {}).get('N', '0')),
            conversation_history=[],
            data_collected={}
        )

        return call_record

    except CallRecordNotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting call record {call_sid}: {e}")
        raise
