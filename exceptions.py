"""
Custom exception classes for the Twilio Voice AI Assistant
"""


class VoiceAssistantException(Exception):
    """Base exception for all voice assistant errors"""
    pass


class AgentNotFoundException(VoiceAssistantException):
    """Raised when an agent is not found in the database"""
    pass


class CallRecordNotFoundException(VoiceAssistantException):
    """Raised when a call record is not found in the database"""
    pass


class DatabaseException(VoiceAssistantException):
    """Raised when a database operation fails"""
    pass


class SessionNotFoundException(VoiceAssistantException):
    """Raised when a session is not found in active sessions"""
    pass


class S3UploadException(VoiceAssistantException):
    """Raised when S3 upload fails"""
    pass


class InvalidAgentConfigException(VoiceAssistantException):
    """Raised when agent configuration is invalid"""
    pass
