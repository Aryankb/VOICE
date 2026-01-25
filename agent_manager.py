"""
Agent manager for fetching and caching agent configurations
"""

import asyncio
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
from database import db_client
from models import AgentConfig
from config import settings
from exceptions import AgentNotFoundException, InvalidAgentConfigException

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


async def get_agent(agent_id: str, use_cache: bool = True) -> AgentConfig:
    """
    Fetch agent configuration from DynamoDB

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

    # Fetch from database
    try:
        item = await db_client.get_item(
            table_name=settings.dynamodb_table_agents,
            key={'agent_id': agent_id}
        )

        if not item:
            logger.warning(f"Agent not found: {agent_id}")
            raise AgentNotFoundException(f"Agent {agent_id} not found")

        # Parse and validate
        try:
            agent_config = AgentConfig.from_dynamodb(item)
        except Exception as e:
            logger.error(f"Invalid agent config for {agent_id}: {e}")
            raise InvalidAgentConfigException(f"Invalid agent configuration: {e}")

        # Validate agent is active
        if agent_config.status != "active":
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


async def get_agent_with_cache(agent_id: str) -> AgentConfig:
    """
    Convenience method to fetch agent with caching enabled

    Args:
        agent_id: Agent identifier

    Returns:
        AgentConfig object
    """
    return await get_agent(agent_id, use_cache=True)


async def create_agent(agent_config: AgentConfig) -> bool:
    """
    Create a new agent in DynamoDB

    Args:
        agent_config: AgentConfig object

    Returns:
        True if successful
    """
    try:
        # Set created_at if not provided
        if not agent_config.created_at:
            agent_config.created_at = datetime.now().isoformat()

        item = agent_config.to_dynamodb()

        success = await db_client.put_item(
            table_name=settings.dynamodb_table_agents,
            item=item,
            condition_expression="attribute_not_exists(agent_id)"  # Prevent overwriting
        )

        if success:
            logger.info(f"Created agent {agent_config.agent_id}: {agent_config.name}")
            # Invalidate cache in case it exists
            _agent_cache.invalidate(agent_config.agent_id)

        return success

    except Exception as e:
        logger.error(f"Error creating agent {agent_config.agent_id}: {e}")
        raise


async def update_agent(agent_id: str, updates: Dict[str, any]) -> bool:
    """
    Update an existing agent in DynamoDB

    Args:
        agent_id: Agent identifier
        updates: Dictionary of fields to update

    Returns:
        True if successful
    """
    try:
        # Add updated_at timestamp
        updates['updated_at'] = datetime.now().isoformat()

        success = await db_client.update_item(
            table_name=settings.dynamodb_table_agents,
            key={'agent_id': agent_id},
            updates=updates,
            condition_expression="attribute_exists(agent_id)"  # Ensure agent exists
        )

        if success:
            logger.info(f"Updated agent {agent_id}")
            # Invalidate cache
            _agent_cache.invalidate(agent_id)

        return success

    except Exception as e:
        logger.error(f"Error updating agent {agent_id}: {e}")
        raise


async def deactivate_agent(agent_id: str) -> bool:
    """
    Deactivate an agent (soft delete)

    Args:
        agent_id: Agent identifier

    Returns:
        True if successful
    """
    return await update_agent(agent_id, {'status': 'inactive'})


async def list_active_agents(limit: int = 100) -> list[AgentConfig]:
    """
    List all active agents

    Args:
        limit: Maximum number of agents to return

    Returns:
        List of AgentConfig objects
    """
    try:
        items = await db_client.query(
            table_name=settings.dynamodb_table_agents,
            key_condition_expression="#status = :status",
            expression_attribute_values={':status': 'active'},
            expression_attribute_names={'#status': 'status'},  # Alias reserved keyword
            index_name='StatusIndex',
            limit=limit,
            scan_forward=False  # Most recent first
        )

        agents = [AgentConfig.from_dynamodb(item) for item in items]
        logger.info(f"Listed {len(agents)} active agents")
        return agents

    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        raise


def get_default_agent_config() -> AgentConfig:
    """
    Get default agent configuration as fallback

    Returns:
        Default AgentConfig object
    """
    return AgentConfig(
        agent_id="default",
        name="Default Agent",
        prompt="You are a helpful AI assistant. Answer questions politely and concisely.",
        voice="Polly.Joanna",
        language="en-US",
        greeting="Hello! I'm your AI assistant. How can I help you today?",
        status="active"
    )


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
