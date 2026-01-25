"""
Call manager for handling call lifecycle and conversation history
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from database import db_client
from models import CallRecord, ConversationMessage
from config import settings
from exceptions import CallRecordNotFoundException

logger = logging.getLogger(__name__)


async def fetch_past_conversations(
    agent_id: str,
    recipient_phone: str,
    limit: int = 5
) -> List[CallRecord]:
    """
    Fetch past conversations for an agent-recipient pair

    Args:
        agent_id: Agent identifier
        recipient_phone: Recipient phone number
        limit: Maximum number of past calls to retrieve (default: 5)

    Returns:
        List of CallRecord objects, most recent first
    """
    try:
        # Query using AgentRecipientIndex GSI
        # We query by agent_id and filter by recipient_phone prefix
        items = await db_client.query(
            table_name=settings.dynamodb_table_calls,
            key_condition_expression="agent_id = :agent_id AND begins_with(agent_recipient_key, :prefix)",
            expression_attribute_values={
                ':agent_id': agent_id,
                ':prefix': f"{agent_id}#{recipient_phone}#"
            },
            index_name='AgentRecipientIndex',
            limit=limit,
            scan_forward=False  # Most recent first (descending order)
        )

        # Parse into CallRecord objects
        past_calls = [CallRecord.from_dynamodb(item) for item in items]

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


async def create_call_record(
    call_sid: str,
    agent_id: str,
    recipient_phone: str,
    caller_phone: str,
    status: str = "initiated"
) -> CallRecord:
    """
    Create initial call record in DynamoDB

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

        # Save to DynamoDB
        await db_client.put_item(
            table_name=settings.dynamodb_table_calls,
            item=call_record.to_dynamodb()
        )

        logger.info(f"Created call record for {call_sid}")
        return call_record

    except Exception as e:
        logger.error(f"Error creating call record for {call_sid}: {e}")
        raise


async def sync_conversation_to_db(
    call_sid: str,
    conversation_history: List[ConversationMessage],
    data_collected: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Sync conversation history to DynamoDB (periodic update)

    Args:
        call_sid: Twilio call SID
        conversation_history: List of conversation messages
        data_collected: Optional data collected so far

    Returns:
        True if successful
    """
    try:
        # Note: 'status' is a reserved keyword, but when used as a dict key
        # in updates, it's handled by update_item internally
        updates = {
            'conversation_history': [
                msg.to_dynamodb() if isinstance(msg, ConversationMessage) else msg
                for msg in conversation_history
            ],
            'status': 'in-progress'
        }

        if data_collected:
            updates['data_collected'] = data_collected

        success = await db_client.update_item(
            table_name=settings.dynamodb_table_calls,
            key={'call_sid': call_sid},
            updates=updates
        )

        if success:
            logger.debug(
                f"Synced conversation for {call_sid}: "
                f"{len(conversation_history)} messages"
            )

        return success

    except Exception as e:
        logger.error(f"Error syncing conversation for {call_sid}: {e}")
        # Don't raise - sync is best-effort
        return False


async def finalize_call(
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
    answered_by: Optional[str] = None
) -> bool:
    """
    Finalize call record with all end-of-call data

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

    Returns:
        True if successful
    """
    try:
        updates = {
            'status': status,
            'ended_at': ended_at
        }

        if duration_seconds is not None:
            updates['duration_seconds'] = duration_seconds

        if ended_by:
            updates['ended_by'] = ended_by

        if conversation_history:
            updates['conversation_history'] = [
                msg.to_dynamodb() if isinstance(msg, ConversationMessage) else msg
                for msg in conversation_history
            ]

        if call_recording_url:
            updates['call_recording_url'] = call_recording_url

        if call_recording_sid:
            updates['call_recording_sid'] = call_recording_sid

        if s3_recording_url:
            updates['s3_recording_url'] = s3_recording_url

        if data_collected:
            updates['data_collected'] = data_collected

        if answered_by:
            updates['answered_by'] = answered_by

        success = await db_client.update_item(
            table_name=settings.dynamodb_table_calls,
            key={'call_sid': call_sid},
            updates=updates
        )

        if success:
            logger.info(
                f"Finalized call {call_sid}: status={status}, "
                f"duration={duration_seconds}s, ended_by={ended_by}"
            )

        return success

    except Exception as e:
        logger.error(f"Error finalizing call {call_sid}: {e}")
        raise


async def get_call_record(call_sid: str) -> CallRecord:
    """
    Get call record from DynamoDB

    Args:
        call_sid: Twilio call SID

    Returns:
        CallRecord object

    Raises:
        CallRecordNotFoundException: If call not found
    """
    try:
        item = await db_client.get_item(
            table_name=settings.dynamodb_table_calls,
            key={'call_sid': call_sid}
        )

        if not item:
            raise CallRecordNotFoundException(f"Call {call_sid} not found")

        return CallRecord.from_dynamodb(item)

    except CallRecordNotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting call record {call_sid}: {e}")
        raise


async def get_calls_by_recipient(
    recipient_phone: str,
    limit: int = 20
) -> List[CallRecord]:
    """
    Get all calls for a recipient phone number

    Args:
        recipient_phone: Phone number
        limit: Maximum number of calls to return

    Returns:
        List of CallRecord objects
    """
    try:
        items = await db_client.query(
            table_name=settings.dynamodb_table_calls,
            key_condition_expression="recipient_phone = :phone",
            expression_attribute_values={':phone': recipient_phone},
            index_name='RecipientIndex',
            limit=limit,
            scan_forward=False  # Most recent first
        )

        calls = [CallRecord.from_dynamodb(item) for item in items]
        logger.info(f"Retrieved {len(calls)} calls for {recipient_phone}")
        return calls

    except Exception as e:
        logger.error(f"Error getting calls for {recipient_phone}: {e}")
        return []


async def get_in_progress_calls(limit: int = 50) -> List[CallRecord]:
    """
    Get all in-progress calls

    Args:
        limit: Maximum number of calls to return

    Returns:
        List of CallRecord objects
    """
    try:
        items = await db_client.query(
            table_name=settings.dynamodb_table_calls,
            key_condition_expression="#status = :status",
            expression_attribute_values={':status': 'in-progress'},
            expression_attribute_names={'#status': 'status'},  # Alias reserved keyword
            index_name='StatusIndex',
            limit=limit,
            scan_forward=False
        )

        calls = [CallRecord.from_dynamodb(item) for item in items]
        logger.info(f"Retrieved {len(calls)} in-progress calls")
        return calls

    except Exception as e:
        logger.error(f"Error getting in-progress calls: {e}")
        return []
