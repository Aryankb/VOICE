"""
Agent manager for fetching and caching agent configurations (SIGMOYD-BACKEND schema)
"""

import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
from tools.dynamo import db_client
from models import AgentConfig, DataCollectionField
from config import settings
from exceptions import AgentNotFoundException, InvalidAgentConfigException
import json

logger = logging.getLogger(__name__)


class AgentCache:
    """Simple in-memory cache for agent data"""

    def __init__(self, ttl_seconds: int = 300):
        self.cache: Dict[str, tuple[AgentConfig, datetime]] = {}
        self.ttl_seconds = ttl_seconds

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        """Get agent from cache if not expired"""
        if agent_id in self.cache:
            agent_config, cached_at = self.cache[agent_id]
            if datetime.now() - cached_at < timedelta(seconds=self.ttl_seconds):
                logger.debug(f"Cache hit for agent {agent_id}")
                return agent_config
            else:
                # Expired, remove from cache
                del self.cache[agent_id]
                logger.debug(f"Cache expired for agent {agent_id}")

        return None

    def set(self, agent_id: str, agent_config: AgentConfig):
        """Store agent in cache"""
        self.cache[agent_id] = (agent_config, datetime.now())
        logger.debug(f"Cached agent {agent_id}")

    def invalidate(self, agent_id: str):
        """Invalidate cache for specific agent"""
        if agent_id in self.cache:
            del self.cache[agent_id]
            logger.debug(f"Invalidated cache for agent {agent_id}")

    def clear(self):
        """Clear entire cache"""
        self.cache.clear()
        logger.debug("Cleared agent cache")


# Global agent cache
_agent_cache = AgentCache(ttl_seconds=settings.agent_cache_ttl_seconds)


def get_agent(agent_id: str, use_cache: bool = True) -> AgentConfig:
    """
    Fetch agent configuration from DynamoDB (SIGMOYD-BACKEND schema - SYNC)

    Args:
        agent_id: Agent identifier
        use_cache: Whether to use cached data (default: True)

    Returns:
        AgentConfig object

    Raises:
        AgentNotFoundException: If agent not found
        InvalidAgentConfigException: If agent config is invalid
    """
    # Check cache first
    if use_cache:
        cached_agent = _agent_cache.get(agent_id)
        if cached_agent:
            return cached_agent

    # Fetch from database (SYNC operation)
    try:
        response = db_client.get_item(
            TableName=settings.dynamodb_table_agents,
            Key={'agent_id': {'S': agent_id}}
        )

        item = response.get('Item')
        if not item:
            logger.warning(f"Agent not found: {agent_id}")
            raise AgentNotFoundException(f"Agent {agent_id} not found")

        # Parse SIGMOYD schema (with type descriptors)
        try:
            # Extract values from DynamoDB format
            agent_id_val = item.get('agent_id', {}).get('S', '')
            name = item.get('name', {}).get('S', 'Unnamed Agent')
            prompt = item.get('prompt', {}).get('S', 'You are a helpful assistant.')
            user_id = item.get('user_id', {}).get('S', '')
            created_at = item.get('created_at', {}).get('S', '')

            # Parse JSON fields
            few_shot = []
            if 'few_shot_examples' in item:
                few_shot_str = item['few_shot_examples'].get('S', '[]')
                few_shot_raw = json.loads(few_shot_str)
                # Parse DynamoDB format if present
                for example in few_shot_raw:
                    if isinstance(example, dict) and 'M' in example:
                        # Extract from DynamoDB Map
                        parsed_example = {}
                        for key, val in example['M'].items():
                            if 'S' in val:
                                parsed_example[key] = val['S']
                        few_shot.append(parsed_example)
                    else:
                        few_shot.append(example)

            mcp_servers = []
            if 'mcp_servers' in item:
                mcp_list = item['mcp_servers'].get('L', [])
                mcp_servers = [s.get('S', '') for s in mcp_list]

            knowledge_files = []
            if 'knowledge_files' in item:
                kf_list = item['knowledge_files'].get('L', [])
                knowledge_files = [f.get('S', '') for f in kf_list]

            data_to_collect = {}
            if 'data_to_collect' in item:
                data_str = item['data_to_collect'].get('S', '{}')
                data_raw = json.loads(data_str)
                # Convert to DataCollectionField format
                for key, value in data_raw.items():
                    if isinstance(value, dict):
                        # Handle nested DynamoDB format {'M': {...}}
                        if 'M' in value:
                            # Extract from DynamoDB Map type
                            field_data = {}
                            for field_key, field_val in value['M'].items():
                                if 'S' in field_val:
                                    field_data[field_key] = field_val['S']
                                elif 'BOOL' in field_val:
                                    field_data[field_key] = field_val['BOOL']
                                elif 'NULL' in field_val:
                                    field_data[field_key] = None
                            data_to_collect[key] = DataCollectionField(**field_data)
                        else:
                            # Already plain dict
                            data_to_collect[key] = DataCollectionField(**value)
                    else:
                        data_to_collect[key] = value

            # Build AgentConfig
            agent_config = AgentConfig(
                agent_id=agent_id_val,
                name=name,
                prompt=prompt,
                few_shot=few_shot,
                voice=item.get('voice', {}).get('S', 'Polly.Joanna'),
                language=item.get('language', {}).get('S', 'en-US'),
                greeting=item.get('greeting', {}).get('S', 'Hello! How can I help you today?'),
                data_to_fill=data_to_collect,
                mcp_config={'servers': mcp_servers},
                s3_file_paths=knowledge_files,
                status=item.get('status', {}).get('S', 'active'),
                created_at=created_at,
                updated_at=item.get('updated_at', {}).get('S')
            )

        except Exception as e:
            logger.error(f"Invalid agent config for {agent_id}: {e}")
            raise InvalidAgentConfigException(f"Invalid agent configuration: {e}")

        # Validate agent is active
        if agent_config.status and agent_config.status != "active":
            logger.warning(f"Agent {agent_id} is not active (status: {agent_config.status})")
            raise AgentNotFoundException(f"Agent {agent_id} is not active")

        # Cache the result
        _agent_cache.set(agent_id, agent_config)

        logger.info(f"Loaded agent {agent_id}: {agent_config.name}")
        return agent_config

    except AgentNotFoundException:
        raise
    except InvalidAgentConfigException:
        raise
    except Exception as e:
        logger.error(f"Error fetching agent {agent_id}: {e}")
        raise


def get_agent_with_cache(agent_id: str) -> AgentConfig:
    """
    Convenience method to fetch agent with caching enabled

    Args:
        agent_id: Agent identifier

    Returns:
        AgentConfig object
    """
    return get_agent(agent_id, use_cache=True)


def invalidate_agent_cache(agent_id: Optional[str] = None):
    """
    Invalidate agent cache

    Args:
        agent_id: Specific agent to invalidate, or None to clear all
    """
    if agent_id:
        _agent_cache.invalidate(agent_id)
    else:
        _agent_cache.clear()
