"""
Pydantic data models for the Twilio Voice AI Assistant
"""

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from decimal import Decimal


class DataCollectionField(BaseModel):
    """Configuration for a single data field to collect"""
    required: bool = True
    prompt: str = Field(..., description="Prompt to ask the user for this field")
    example: Optional[str] = None
    validation_pattern: Optional[str] = None


class AgentConfig(BaseModel):
    """Agent configuration model"""
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Human-readable agent name")
    prompt: str = Field(..., description="System prompt for the agent")
    few_shot: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Few-shot examples for the agent"
    )
    voice: str = Field(
        default="Polly.Joanna",
        description="Twilio voice to use (e.g., Polly.Joanna, Polly.Aditi)"
    )
    language: str = Field(
        default="en-US",
        description="Language code (e.g., en-US, hi-IN)"
    )
    greeting: str = Field(
        default="Hello! How can I help you today?",
        description="Initial greeting message"
    )
    data_to_fill: Dict[str, DataCollectionField] = Field(
        default_factory=dict,
        description="Data fields to collect from the caller"
    )
    mcp_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="MCP server configuration"
    )
    s3_file_paths: List[str] = Field(
        default_factory=list,
        description="S3 paths for agent-specific files"
    )
    status: str = Field(
        default="active",
        description="Agent status (active, inactive, archived)"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Creation timestamp"
    )
    updated_at: Optional[str] = None

    @field_validator('voice')
    @classmethod
    def validate_voice(cls, v: str) -> str:
        """Validate Twilio voice format"""
        valid_voices = [
            "Polly.Joanna", "Polly.Matthew", "Polly.Aditi", "Polly.Amy",
            "Polly.Brian", "Polly.Emma", "Polly.Geraint", "Polly.Ivy",
            "Polly.Joey", "Polly.Justin", "Polly.Kendra", "Polly.Kimberly",
            "Polly.Nicole", "Polly.Russell", "Polly.Salli", "woman", "man", "alice"
        ]
        # Accept any Polly voice or basic voices
        if v not in valid_voices and not v.startswith("Polly."):
            raise ValueError(f"Invalid voice: {v}. Must be a valid Twilio voice.")
        return v

    @field_validator('language')
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate language code format"""
        # Basic validation - should be in format xx-XX
        if len(v) != 5 or v[2] != '-':
            raise ValueError(f"Invalid language code: {v}. Expected format: xx-XX (e.g., en-US)")
        return v

    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate agent status"""
        valid_statuses = ["active", "inactive", "archived"]
        if v not in valid_statuses:
            raise ValueError(f"Invalid status: {v}. Must be one of {valid_statuses}")
        return v

    def to_dynamodb(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format"""
        item = self.model_dump()
        # Convert nested Pydantic models to dict
        if "data_to_fill" in item:
            item["data_to_fill"] = {
                key: value.model_dump() if isinstance(value, DataCollectionField) else value
                for key, value in item["data_to_fill"].items()
            }
        return item

    @classmethod
    def from_dynamodb(cls, item: Dict[str, Any]) -> 'AgentConfig':
        """Create from DynamoDB item"""
        # Convert data_to_fill back to DataCollectionField objects
        if "data_to_fill" in item:
            item["data_to_fill"] = {
                key: DataCollectionField(**value) if isinstance(value, dict) else value
                for key, value in item["data_to_fill"].items()
            }
        return cls(**item)


class ConversationMessage(BaseModel):
    """Single message in a conversation"""
    role: str = Field(..., description="Message role (user, assistant)")
    content: str = Field(..., description="Message content")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Message timestamp"
    )
    confidence: Optional[float] = Field(
        None,
        description="Speech recognition confidence (0-1) for user messages"
    )
    recording_url: Optional[str] = Field(
        None,
        description="Twilio recording URL for user messages"
    )
    recording_sid: Optional[str] = Field(
        None,
        description="Twilio recording SID for user messages"
    )

    @field_validator('role')
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate message role"""
        valid_roles = ["user", "assistant", "system"]
        if v not in valid_roles:
            raise ValueError(f"Invalid role: {v}. Must be one of {valid_roles}")
        return v

    def to_dynamodb(self) -> Dict[str, Any]:
        """Convert to DynamoDB format"""
        from decimal import Decimal
        item = self.model_dump(exclude_none=True)
        # Convert float confidence to Decimal for DynamoDB
        if "confidence" in item and isinstance(item["confidence"], float):
            item["confidence"] = Decimal(str(item["confidence"]))
        return item


class CallRecord(BaseModel):
    """Complete call record model"""
    call_sid: str = Field(..., description="Twilio call SID")
    agent_id: str = Field(..., description="Agent ID used for this call")
    recipient_phone: str = Field(..., description="Phone number called")
    caller_phone: str = Field(..., description="Phone number calling from")
    status: str = Field(
        default="initiated",
        description="Call status (initiated, in-progress, completed, failed, busy, no-answer)"
    )
    started_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Call start timestamp"
    )
    ended_at: Optional[str] = None
    duration_seconds: Optional[int] = Field(
        None,
        description="Call duration in seconds"
    )
    ended_by: Optional[str] = Field(
        None,
        description="Who ended the call (user, system_complete, system_timeout, unknown)"
    )
    conversation_history: List[ConversationMessage] = Field(
        default_factory=list,
        description="Full conversation history"
    )
    call_recording_url: Optional[str] = Field(
        None,
        description="Twilio recording URL"
    )
    call_recording_sid: Optional[str] = Field(
        None,
        description="Twilio recording SID"
    )
    s3_recording_url: Optional[str] = Field(
        None,
        description="S3 URL for archived recording"
    )
    data_collected: Dict[str, Any] = Field(
        default_factory=dict,
        description="Data collected during the call"
    )
    answered_by: Optional[str] = Field(
        None,
        description="Who answered (human, machine)"
    )
    # GSI keys for queries
    agent_recipient_key: Optional[str] = Field(
        None,
        description="Composite key for agent+recipient queries (agent_id#recipient_phone#timestamp)"
    )

    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate call status"""
        valid_statuses = [
            "initiated", "ringing", "in-progress", "completed",
            "failed", "busy", "no-answer", "canceled"
        ]
        if v not in valid_statuses:
            raise ValueError(f"Invalid status: {v}. Must be one of {valid_statuses}")
        return v

    def to_dynamodb(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format"""
        item = self.model_dump(exclude_none=True)

        # Convert conversation_history to DynamoDB format
        if "conversation_history" in item:
            item["conversation_history"] = [
                msg.to_dynamodb() if isinstance(msg, ConversationMessage) else msg
                for msg in self.conversation_history
            ]

        # Generate composite key for GSI-1 (AgentRecipientIndex)
        if not item.get("agent_recipient_key"):
            item["agent_recipient_key"] = (
                f"{self.agent_id}#{self.recipient_phone}#{self.started_at}"
            )

        return item

    @classmethod
    def from_dynamodb(cls, item: Dict[str, Any]) -> 'CallRecord':
        """Create from DynamoDB item"""
        # Convert conversation_history back to ConversationMessage objects
        if "conversation_history" in item:
            item["conversation_history"] = [
                ConversationMessage(**msg) if isinstance(msg, dict) else msg
                for msg in item["conversation_history"]
            ]
        return cls(**item)


class SessionData(BaseModel):
    """In-memory session data structure"""
    call_sid: str
    agent_id: str
    agent_data: AgentConfig
    past_conversations: List[CallRecord] = Field(default_factory=list)
    to: str
    from_: str = Field(..., alias="from")
    conversation_history: List[ConversationMessage] = Field(default_factory=list)
    data_collected: Dict[str, Any] = Field(default_factory=dict)
    message_count: int = 0
    last_sync_count: int = 0
    no_input_count: int = 0
    ended_by: Optional[str] = None
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    class Config:
        populate_by_name = True  # Allow both 'from_' and 'from'

    def should_sync(self, sync_frequency: int = 5) -> bool:
        """Check if session should be synced to database"""
        return (self.message_count - self.last_sync_count) >= sync_frequency

    def mark_synced(self):
        """Mark session as synced"""
        self.last_sync_count = self.message_count


class VoiceAgentRequest(BaseModel):
    """Request model for creating/updating voice agents (voice.py API)"""
    goal: str = Field(..., description="Agent goal/prompt (used as name and system prompt)")
    few_shot_examples: Optional[List[Dict[str, str]]] = Field(
        None,
        description="Few-shot examples for the agent"
    )
    mcp_servers: Optional[List[str]] = Field(
        None,
        description="List of MCP server names/URLs"
    )
    knowledge_files: Optional[List[str]] = Field(
        None,
        description="List of S3 paths or file URLs for knowledge base"
    )
    data_to_collect: Optional[Dict[str, Union[str, Dict[str, Any]]]] = Field(
        None,
        description="Data fields to collect from caller"
    )
    phone_numbers: Optional[List[str]] = Field(
        None,
        description="List of phone numbers to link to this agent"
    )
