"""
CLI tool for managing agents in DynamoDB

Usage:
    python scripts/manage_agents.py list
    python scripts/manage_agents.py get <agent_id>
    python scripts/manage_agents.py create --config agent_config.json
    python scripts/manage_agents.py deactivate <agent_id>
"""

import sys
import os
import asyncio
import json
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import AgentConfig
from agent_manager import (
    get_agent,
    create_agent,
    update_agent,
    deactivate_agent,
    list_active_agents
)
from config import settings


async def list_agents_cmd():
    """List all active agents"""
    print("=" * 60)
    print("Active Agents")
    print("=" * 60)

    try:
        agents = await list_active_agents(limit=100)

        if not agents:
            print("No active agents found.")
            return

        for agent in agents:
            print(f"\nAgent ID: {agent.agent_id}")
            print(f"  Name: {agent.name}")
            print(f"  Voice: {agent.voice}")
            print(f"  Language: {agent.language}")
            print(f"  Greeting: {agent.greeting[:60]}...")
            print(f"  Data to collect: {', '.join(agent.data_to_fill.keys()) if agent.data_to_fill else 'None'}")
            print(f"  Created: {agent.created_at}")

        print("\n" + "=" * 60)
        print(f"Total: {len(agents)} active agents")
        print("=" * 60)

    except Exception as e:
        print(f"✗ Error listing agents: {e}")
        sys.exit(1)


async def get_agent_cmd(agent_id: str):
    """Get detailed agent information"""
    print("=" * 60)
    print(f"Agent Details: {agent_id}")
    print("=" * 60)

    try:
        agent = await get_agent(agent_id, use_cache=False)

        print(f"\nAgent ID: {agent.agent_id}")
        print(f"Name: {agent.name}")
        print(f"Status: {agent.status}")
        print(f"Voice: {agent.voice}")
        print(f"Language: {agent.language}")
        print(f"\nGreeting:")
        print(f"  {agent.greeting}")
        print(f"\nPrompt:")
        print(f"  {agent.prompt}")

        if agent.few_shot:
            print(f"\nFew-shot Examples ({len(agent.few_shot)}):")
            for i, example in enumerate(agent.few_shot, 1):
                print(f"  Example {i}:")
                print(f"    User: {example.get('user', '')}")
                print(f"    Assistant: {example.get('assistant', '')}")

        if agent.data_to_fill:
            print(f"\nData to Collect:")
            for field_name, field_config in agent.data_to_fill.items():
                if isinstance(field_config, dict):
                    required = field_config.get("required", True)
                    prompt = field_config.get("prompt", "")
                else:
                    required = field_config.required
                    prompt = field_config.prompt
                req_str = "REQUIRED" if required else "optional"
                print(f"  {field_name} ({req_str}): {prompt}")

        print(f"\nCreated: {agent.created_at}")
        if agent.updated_at:
            print(f"Updated: {agent.updated_at}")

        print("=" * 60)

    except Exception as e:
        print(f"✗ Error getting agent: {e}")
        sys.exit(1)


async def create_agent_cmd(config_file: str):
    """Create agent from JSON config file"""
    print("=" * 60)
    print("Creating Agent")
    print("=" * 60)

    try:
        # Load config from file
        with open(config_file, 'r') as f:
            config_data = json.load(f)

        # Parse into AgentConfig
        agent = AgentConfig(**config_data)

        # Create in database
        await create_agent(agent)

        print(f"✓ Successfully created agent: {agent.agent_id} ({agent.name})")
        print("=" * 60)

    except FileNotFoundError:
        print(f"✗ Config file not found: {config_file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON in config file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error creating agent: {e}")
        sys.exit(1)


async def deactivate_agent_cmd(agent_id: str):
    """Deactivate an agent"""
    print("=" * 60)
    print(f"Deactivating Agent: {agent_id}")
    print("=" * 60)

    try:
        success = await deactivate_agent(agent_id)

        if success:
            print(f"✓ Successfully deactivated agent: {agent_id}")
        else:
            print(f"⚠ Agent {agent_id} may not exist or is already inactive")

        print("=" * 60)

    except Exception as e:
        print(f"✗ Error deactivating agent: {e}")
        sys.exit(1)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Manage agents in DynamoDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/manage_agents.py list
  python scripts/manage_agents.py get customer-support-001
  python scripts/manage_agents.py create --config my_agent.json
  python scripts/manage_agents.py deactivate old-agent-001
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # List command
    subparsers.add_parser('list', help='List all active agents')

    # Get command
    get_parser = subparsers.add_parser('get', help='Get agent details')
    get_parser.add_argument('agent_id', help='Agent ID to retrieve')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create new agent')
    create_parser.add_argument('--config', required=True, help='Path to JSON config file')

    # Deactivate command
    deactivate_parser = subparsers.add_parser('deactivate', help='Deactivate an agent')
    deactivate_parser.add_argument('agent_id', help='Agent ID to deactivate')

    args = parser.parse_args()

    if not settings.enable_dynamodb:
        print("⚠ DynamoDB is disabled in settings. Enable it in .env first.")
        sys.exit(1)

    # Execute command
    if args.command == 'list':
        asyncio.run(list_agents_cmd())
    elif args.command == 'get':
        asyncio.run(get_agent_cmd(args.agent_id))
    elif args.command == 'create':
        asyncio.run(create_agent_cmd(args.config))
    elif args.command == 'deactivate':
        asyncio.run(deactivate_agent_cmd(args.agent_id))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
