from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Twilio Configuration
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str

    # Server Configuration
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    public_url: str

    # Audio Processing
    silence_threshold_seconds: float = 4.0
    audio_sample_rate: int = 8000

    # AWS Configuration
    aws_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None  # Optional - uses boto3 default credential chain
    aws_secret_access_key: Optional[str] = None  # Optional - uses boto3 default credential chain

    # DynamoDB Configuration (matching voice.py schema)
    dynamodb_table_agents: str = "Agents"
    dynamodb_table_calls: str = "Calls"
    dynamodb_table_phone_numbers: str = "PhoneNumbers"
    dynamodb_table_agent_number_mapping: str = "AgentNumberMapping"

    # S3 Configuration
    s3_bucket_recordings: str = "voice-assistant-recordings"
    s3_recordings_prefix: str = "recordings/"

    # Session Management
    session_sync_frequency: int = 5  # Sync to DB every N messages
    agent_cache_ttl_seconds: int = 300  # Agent data cache TTL (5 minutes)

    # Feature Flags
    enable_dynamodb: bool = True  # Enable/disable DynamoDB integration
    enable_s3_upload: bool = True  # Enable/disable S3 recording upload

    # LLM Configuration
    openai_api_key: Optional[str] = None  # OpenAI API key for GPT-4
    use_openai: bool = False  # Enable OpenAI integration
    openai_model: str = "gpt-4"  # Model to use (gpt-4, gpt-3.5-turbo, etc.)

    # Local LLM Configuration (Ollama)
    use_local_llm: bool = True  # Enable local LLM (Ollama)
    ollama_host: str = "http://localhost:11434"  # Ollama API endpoint
    ollama_model: str = "qwen2.5-coder:32b-instruct-q4_K_M"  # Model name
    ollama_timeout: int = 120  # Timeout in seconds for LLM responses

    # Local TTS Configuration
    use_local_tts: bool = True  # Enable local TTS
    tts_engine: str = "xtts"  # Options: xtts, melo
    tts_output_dir: str = "./tts_output"  # Directory for generated audio files
    tts_sample_rate: int = 8000  # Twilio requires 8kHz for mulaw
    tts_cleanup_delay: int = 300  # Delete audio files after N seconds

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
