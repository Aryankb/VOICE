"""
Session manager for hybrid in-memory + database session management
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from models import SessionData, ConversationMessage, AgentConfig, CallRecord
from call_manager import sync_conversation_to_db, get_call_record
from config import settings
from exceptions import SessionNotFoundException

logger = logging.getLogger(__name__)

# Thread-safe lock for session updates
_session_locks: Dict[str, asyncio.Lock] = {}


def _get_lock(call_sid: str) -> asyncio.Lock:
    """Get or create a lock for a specific session"""
    if call_sid not in _session_locks:
        _session_locks[call_sid] = asyncio.Lock()
    return _session_locks[call_sid]


async def create_session(
    call_sid: str,
    agent_id: str,
    agent_data: AgentConfig,
    past_conversations: list[CallRecord],
    to: str,
    from_: str,
    active_sessions: Dict[str, dict]
) -> SessionData:
    """
    Create a new session in memory

    Args:
        call_sid: Twilio call SID
        agent_id: Agent identifier
        agent_data: Full agent configuration
        past_conversations: Past conversation history
        to: Phone number being called
        from_: Phone number calling from
        active_sessions: Reference to active_sessions dict

    Returns:
        SessionData object
    """
    try:
        session_data = SessionData(
            call_sid=call_sid,
            agent_id=agent_id,
            agent_data=agent_data,
            past_conversations=past_conversations,
            to=to,
            from_=from_,
            conversation_history=[],
            data_collected={},
            message_count=0,
            last_sync_count=0,
            no_input_count=0,
            started_at=datetime.now().isoformat()
        )

        # Store in active_sessions dict as plain dict for compatibility
        active_sessions[call_sid] = session_data.model_dump(by_alias=True)

        logger.info(
            f"Created session for {call_sid}: agent={agent_id}, "
            f"past_conversations={len(past_conversations)}"
        )

        return session_data

    except Exception as e:
        logger.error(f"Error creating session for {call_sid}: {e}")
        raise


async def get_session(
    call_sid: str,
    active_sessions: Dict[str, dict]
) -> Dict[str, Any]:
    """
    Get session from memory with recovery fallback

    Args:
        call_sid: Twilio call SID
        active_sessions: Reference to active_sessions dict

    Returns:
        Session dict

    Raises:
        SessionNotFoundException: If session not found and recovery fails
    """
    if call_sid in active_sessions:
        return active_sessions[call_sid]

    # Try to recover from database
    logger.warning(f"Session {call_sid} not in memory, attempting recovery")

    try:
        call_record = await get_call_record(call_sid)

        # Reconstruct minimal session (won't have agent_data or past_conversations)
        recovered_session = {
            "call_sid": call_sid,
            "agent_id": call_record.agent_id,
            "to": call_record.recipient_phone,
            "from": call_record.caller_phone,
            "conversation_history": [
                msg.model_dump() if isinstance(msg, ConversationMessage) else msg
                for msg in call_record.conversation_history
            ],
            "data_collected": call_record.data_collected,
            "message_count": len(call_record.conversation_history),
            "last_sync_count": len(call_record.conversation_history),
            "no_input_count": 0,
            "started_at": call_record.started_at,
            "recovered": True
        }

        active_sessions[call_sid] = recovered_session
        logger.info(f"Recovered session for {call_sid} from database")

        return recovered_session

    except Exception as e:
        logger.error(f"Failed to recover session for {call_sid}: {e}")
        raise SessionNotFoundException(f"Session {call_sid} not found")


async def update_session(
    call_sid: str,
    updates: Dict[str, Any],
    active_sessions: Dict[str, dict]
) -> bool:
    """
    Thread-safe session update

    Args:
        call_sid: Twilio call SID
        updates: Dictionary of updates to apply
        active_sessions: Reference to active_sessions dict

    Returns:
        True if successful
    """
    lock = _get_lock(call_sid)

    async with lock:
        try:
            if call_sid not in active_sessions:
                logger.warning(f"Cannot update non-existent session {call_sid}")
                return False

            # Apply updates
            active_sessions[call_sid].update(updates)

            logger.debug(f"Updated session {call_sid}: {list(updates.keys())}")
            return True

        except Exception as e:
            logger.error(f"Error updating session {call_sid}: {e}")
            return False


async def sync_session_to_db(
    call_sid: str,
    active_sessions: Dict[str, dict],
    force: bool = False
) -> bool:
    """
    Sync session to database if sync threshold is met

    Args:
        call_sid: Twilio call SID
        active_sessions: Reference to active_sessions dict
        force: Force sync regardless of threshold

    Returns:
        True if synced, False if skipped or failed
    """
    try:
        session = active_sessions.get(call_sid)
        if not session:
            return False

        message_count = session.get("message_count", 0)
        last_sync_count = session.get("last_sync_count", 0)

        # Check if sync is needed
        should_sync = (
            force or
            (message_count - last_sync_count) >= settings.session_sync_frequency
        )

        if not should_sync:
            logger.debug(f"Skipping sync for {call_sid}: threshold not met")
            return False

        # Convert conversation_history to ConversationMessage objects
        conversation_history = [
            ConversationMessage(**msg) if isinstance(msg, dict) else msg
            for msg in session.get("conversation_history", [])
        ]

        # Sync to database
        success = await sync_conversation_to_db(
            call_sid=call_sid,
            conversation_history=conversation_history,
            data_collected=session.get("data_collected")
        )

        if success:
            # Update last sync count
            session["last_sync_count"] = message_count
            logger.info(
                f"Synced session {call_sid} to DB: "
                f"{message_count} messages"
            )

        return success

    except Exception as e:
        logger.error(f"Error syncing session {call_sid}: {e}")
        return False


async def cleanup_session(
    call_sid: str,
    active_sessions: Dict[str, dict]
) -> bool:
    """
    Delete session from memory

    Args:
        call_sid: Twilio call SID
        active_sessions: Reference to active_sessions dict

    Returns:
        True if cleaned up
    """
    try:
        if call_sid in active_sessions:
            del active_sessions[call_sid]
            logger.info(f"Cleaned up session {call_sid}")

        # Clean up lock
        if call_sid in _session_locks:
            del _session_locks[call_sid]

        return True

    except Exception as e:
        logger.error(f"Error cleaning up session {call_sid}: {e}")
        return False


def is_data_collection_complete(session: Dict[str, Any]) -> bool:
    """
    Check if all required data has been collected

    Args:
        session: Session dict

    Returns:
        True if all required data is collected
    """
    try:
        agent_data = session.get("agent_data")
        if not agent_data:
            return False

        data_to_fill = agent_data.get("data_to_fill", {})
        if not data_to_fill:
            # No data collection required
            return False

        data_collected = session.get("data_collected", {})

        # Check if all required fields are collected
        for field_name, field_config in data_to_fill.items():
            if isinstance(field_config, dict):
                is_required = field_config.get("required", True)
            else:
                is_required = field_config.required

            if is_required and field_name not in data_collected:
                return False

        logger.info(f"Data collection complete for session {session.get('call_sid')}")
        return True

    except Exception as e:
        logger.error(f"Error checking data collection status: {e}")
        return False


def detect_goodbye_intent(user_input: str) -> bool:
    """
    Detect if user wants to end the call

    Args:
        user_input: User's speech input

    Returns:
        True if goodbye intent detected
    """
    goodbye_phrases = [
        "goodbye", "bye", "bye bye", "good bye",
        "thank you", "thanks", "that's all", "that is all",
        "nothing else", "i'm done", "im done", "done",
        "hang up", "end call"
    ]

    user_lower = user_input.lower().strip()

    # Check for exact or partial matches
    for phrase in goodbye_phrases:
        if phrase in user_lower:
            logger.info(f"Goodbye intent detected: '{user_input}'")
            return True

    return False
