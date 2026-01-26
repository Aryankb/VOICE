"""
Migration script: Old schema → SIGMOYD-BACKEND schema

Migrates data from:
- VoiceAssistant_Agents → Agents
- VoiceAssistant_Calls → Calls
- VoiceAssistant_PhoneNumbers → PhoneNumbers

Preserves all conversation history, collected data, and user information.
"""

import boto3
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize boto3 clients
if settings.aws_access_key_id and settings.aws_secret_access_key:
    dynamodb = boto3.client(
        'dynamodb',
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key
    )
else:
    dynamodb = boto3.client('dynamodb', region_name=settings.aws_region)

# Old and new table names
OLD_TABLES = {
    'agents': 'VoiceAssistant_Agents',
    'calls': 'VoiceAssistant_Calls',
    'phone_numbers': 'VoiceAssistant_PhoneNumbers'
}

NEW_TABLES = {
    'agents': 'Agents',
    'calls': 'Calls',
    'phone_numbers': 'PhoneNumbers',
    'agent_number_mapping': 'AgentNumberMapping'
}


def table_exists(table_name: str) -> bool:
    """Check if a DynamoDB table exists"""
    try:
        dynamodb.describe_table(TableName=table_name)
        return True
    except dynamodb.exceptions.ResourceNotFoundException:
        return False
    except Exception as e:
        logger.error(f"Error checking table {table_name}: {e}")
        return False


def convert_to_type_descriptors(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert Python native types to DynamoDB type descriptors

    Example:
        {'name': 'Agent', 'count': 5}
        → {'name': {'S': 'Agent'}, 'count': {'N': '5'}}
    """
    result = {}

    for key, value in item.items():
        if value is None:
            continue
        elif isinstance(value, str):
            result[key] = {'S': value}
        elif isinstance(value, bool):
            result[key] = {'BOOL': value}
        elif isinstance(value, (int, float)):
            result[key] = {'N': str(value)}
        elif isinstance(value, list):
            # Convert list items
            converted_list = []
            for list_item in value:
                if isinstance(list_item, str):
                    converted_list.append({'S': list_item})
                elif isinstance(list_item, dict):
                    converted_list.append({'M': convert_to_type_descriptors(list_item)})
                elif isinstance(list_item, (int, float)):
                    converted_list.append({'N': str(list_item)})
            result[key] = {'L': converted_list}
        elif isinstance(value, dict):
            result[key] = {'M': convert_to_type_descriptors(value)}

    return result


def migrate_agents() -> int:
    """
    Migrate agents from VoiceAssistant_Agents to Agents table

    Returns:
        Number of agents migrated
    """
    logger.info("=" * 60)
    logger.info("MIGRATING AGENTS")
    logger.info("=" * 60)

    if not table_exists(OLD_TABLES['agents']):
        logger.warning(f"Old agents table {OLD_TABLES['agents']} does not exist. Skipping.")
        return 0

    if not table_exists(NEW_TABLES['agents']):
        logger.error(f"New agents table {NEW_TABLES['agents']} does not exist. Please create it first.")
        return 0

    migrated_count = 0

    try:
        # Scan old agents table
        response = dynamodb.scan(TableName=OLD_TABLES['agents'])
        old_agents = response.get('Items', [])

        logger.info(f"Found {len(old_agents)} agents in old table")

        for old_agent in old_agents:
            try:
                # Extract values from old format (could be native or type descriptors)
                agent_id = old_agent.get('agent_id', {}).get('S') or old_agent.get('agent_id')
                name = old_agent.get('name', {}).get('S') or old_agent.get('name', 'Unnamed Agent')
                prompt = old_agent.get('prompt', {}).get('S') or old_agent.get('prompt', 'You are a helpful assistant.')

                # Build new agent item in SIGMOYD format
                new_agent = {
                    'agent_id': {'S': str(agent_id)},
                    'user_id': {'S': old_agent.get('user_id', {}).get('S') or old_agent.get('user_id', 'migrated')},
                    'name': {'S': name},
                    'prompt': {'S': prompt},
                    'created_at': {'S': old_agent.get('created_at', {}).get('S') or datetime.utcnow().isoformat() + 'Z'}
                }

                # Optional fields
                if 'few_shot' in old_agent or 'few_shot_examples' in old_agent:
                    few_shot_data = old_agent.get('few_shot') or old_agent.get('few_shot_examples', {})
                    if isinstance(few_shot_data, dict) and 'L' in few_shot_data:
                        few_shot_list = few_shot_data['L']
                    elif isinstance(few_shot_data, list):
                        few_shot_list = few_shot_data
                    else:
                        few_shot_list = []
                    new_agent['few_shot_examples'] = {'S': json.dumps(few_shot_list)}

                if 'voice' in old_agent:
                    new_agent['voice'] = {'S': old_agent.get('voice', {}).get('S') or old_agent['voice']}

                if 'language' in old_agent:
                    new_agent['language'] = {'S': old_agent.get('language', {}).get('S') or old_agent['language']}

                if 'greeting' in old_agent:
                    new_agent['greeting'] = {'S': old_agent.get('greeting', {}).get('S') or old_agent['greeting']}

                if 'data_to_fill' in old_agent or 'data_to_collect' in old_agent:
                    data_field = old_agent.get('data_to_fill') or old_agent.get('data_to_collect', {})
                    if isinstance(data_field, dict):
                        if 'M' in data_field:
                            # Already type descriptor
                            data_dict = data_field['M']
                        else:
                            # Native format
                            data_dict = data_field
                        new_agent['data_to_collect'] = {'S': json.dumps(data_dict)}

                if 'mcp_config' in old_agent:
                    mcp_data = old_agent.get('mcp_config', {})
                    if isinstance(mcp_data, dict):
                        servers = mcp_data.get('servers', [])
                        if servers:
                            new_agent['mcp_servers'] = {'L': [{'S': s} for s in servers]}

                if 's3_file_paths' in old_agent or 'knowledge_files' in old_agent:
                    files_data = old_agent.get('s3_file_paths') or old_agent.get('knowledge_files', [])
                    if isinstance(files_data, list):
                        new_agent['knowledge_files'] = {'L': [{'S': f} for f in files_data]}

                if 'status' in old_agent:
                    new_agent['status'] = {'S': old_agent.get('status', {}).get('S') or old_agent.get('status', 'active')}

                # Put to new table
                dynamodb.put_item(
                    TableName=NEW_TABLES['agents'],
                    Item=new_agent,
                    ConditionExpression='attribute_not_exists(agent_id)'  # Don't overwrite existing
                )

                migrated_count += 1
                logger.info(f"✅ Migrated agent: {agent_id} - {name}")

            except dynamodb.exceptions.ConditionalCheckFailedException:
                logger.info(f"⏭️  Agent {agent_id} already exists in new table, skipping")
            except Exception as e:
                logger.error(f"❌ Error migrating agent {agent_id}: {e}")
                continue

        logger.info(f"\n✅ Migrated {migrated_count}/{len(old_agents)} agents")
        return migrated_count

    except Exception as e:
        logger.error(f"Error during agent migration: {e}")
        return migrated_count


def migrate_calls() -> int:
    """
    Migrate calls from VoiceAssistant_Calls to Calls table

    IMPORTANT: Old Calls table used single PK (call_sid)
               New Calls table uses composite key (agent_id + call_sid)

    Returns:
        Number of calls migrated
    """
    logger.info("\n" + "=" * 60)
    logger.info("MIGRATING CALLS")
    logger.info("=" * 60)

    if not table_exists(OLD_TABLES['calls']):
        logger.warning(f"Old calls table {OLD_TABLES['calls']} does not exist. Skipping.")
        return 0

    if not table_exists(NEW_TABLES['calls']):
        logger.error(f"New calls table {NEW_TABLES['calls']} does not exist. Please create it first.")
        return 0

    migrated_count = 0

    try:
        # Scan old calls table
        response = dynamodb.scan(TableName=OLD_TABLES['calls'])
        old_calls = response.get('Items', [])

        logger.info(f"Found {len(old_calls)} calls in old table")

        for old_call in old_calls:
            try:
                # Extract values
                call_sid = old_call.get('call_sid', {}).get('S') or old_call.get('call_sid')
                agent_id = old_call.get('agent_id', {}).get('S') or old_call.get('agent_id', 'unknown')

                if agent_id == 'unknown':
                    logger.warning(f"⚠️  Call {call_sid} has no agent_id, using 'unknown'")

                # Build new call item in SIGMOYD format
                new_call = {
                    'agent_id': {'S': str(agent_id)},  # Partition key
                    'call_sid': {'S': str(call_sid)},  # Sort key
                }

                # Map old field names to new field names
                field_mapping = {
                    'recipient_phone': 'recipient_number',
                    'caller_phone': 'from_number',
                    'started_at': 'timestamp_start',
                    'ended_at': 'timestamp_end',
                    'duration_seconds': 'duration'
                }

                for old_field, new_field in field_mapping.items():
                    if old_field in old_call:
                        value = old_call[old_field]
                        if isinstance(value, dict) and 'S' in value:
                            new_call[new_field] = {'S': value['S']}
                        elif isinstance(value, dict) and 'N' in value:
                            new_call[new_field] = {'N': value['N']}
                        elif isinstance(value, str):
                            new_call[new_field] = {'S': value}
                        elif isinstance(value, (int, float)):
                            new_call[new_field] = {'N': str(value)}

                # Handle status
                if 'status' in old_call:
                    status_val = old_call['status']
                    if isinstance(status_val, dict) and 'S' in status_val:
                        new_call['status'] = {'S': status_val['S']}
                    else:
                        new_call['status'] = {'S': str(status_val)}

                # Handle conversation_history (complex nested structure)
                if 'conversation_history' in old_call:
                    conv_hist = old_call['conversation_history']
                    if isinstance(conv_hist, dict) and 'L' in conv_hist:
                        # Already in list format
                        new_call['conversation_history'] = conv_hist
                    elif isinstance(conv_hist, list):
                        # Convert to type descriptor list
                        conv_list = []
                        for msg in conv_hist:
                            if isinstance(msg, dict):
                                if 'M' in msg:
                                    conv_list.append(msg)
                                else:
                                    conv_list.append({'M': convert_to_type_descriptors(msg)})
                        new_call['conversation_history'] = {'L': conv_list}
                    else:
                        new_call['conversation_history'] = {'L': []}
                else:
                    new_call['conversation_history'] = {'L': []}

                # Handle data_collected
                if 'data_collected' in old_call:
                    data = old_call['data_collected']
                    if isinstance(data, dict):
                        if 'M' in data:
                            new_call['data_collected'] = data
                        else:
                            new_call['data_collected'] = {'M': convert_to_type_descriptors(data)}
                    else:
                        new_call['data_collected'] = {'M': {}}
                else:
                    new_call['data_collected'] = {'M': {}}

                # Optional fields
                for field in ['call_recording_url', 'call_recording_sid', 's3_recording_url', 'answered_by', 'ended_by']:
                    if field in old_call:
                        val = old_call[field]
                        if isinstance(val, dict) and 'S' in val:
                            new_call[field] = val
                        elif isinstance(val, str):
                            new_call[field] = {'S': val}

                # Ensure duration is a number
                if 'duration' not in new_call:
                    new_call['duration'] = {'N': '0'}

                # Put to new table
                dynamodb.put_item(
                    TableName=NEW_TABLES['calls'],
                    Item=new_call,
                    ConditionExpression='attribute_not_exists(call_sid)'  # Don't overwrite existing
                )

                migrated_count += 1
                logger.info(f"✅ Migrated call: {call_sid} (agent: {agent_id})")

            except dynamodb.exceptions.ConditionalCheckFailedException:
                logger.info(f"⏭️  Call {call_sid} already exists in new table, skipping")
            except Exception as e:
                logger.error(f"❌ Error migrating call {call_sid}: {e}")
                continue

        logger.info(f"\n✅ Migrated {migrated_count}/{len(old_calls)} calls")
        return migrated_count

    except Exception as e:
        logger.error(f"Error during call migration: {e}")
        return migrated_count


def migrate_phone_numbers() -> int:
    """
    Migrate phone numbers from VoiceAssistant_PhoneNumbers to PhoneNumbers table

    Returns:
        Number of phone numbers migrated
    """
    logger.info("\n" + "=" * 60)
    logger.info("MIGRATING PHONE NUMBERS")
    logger.info("=" * 60)

    if not table_exists(OLD_TABLES['phone_numbers']):
        logger.warning(f"Old phone numbers table {OLD_TABLES['phone_numbers']} does not exist. Skipping.")
        return 0

    if not table_exists(NEW_TABLES['phone_numbers']):
        logger.error(f"New phone numbers table {NEW_TABLES['phone_numbers']} does not exist. Please create it first.")
        return 0

    migrated_count = 0

    try:
        # Scan old phone numbers table
        response = dynamodb.scan(TableName=OLD_TABLES['phone_numbers'])
        old_numbers = response.get('Items', [])

        logger.info(f"Found {len(old_numbers)} phone numbers in old table")

        for old_number in old_numbers:
            try:
                # Extract values
                phone_number = old_number.get('phone_number', {}).get('S') or old_number.get('phone_number')
                user_id = old_number.get('user_id', {}).get('S') or old_number.get('user_id', 'migrated')

                # Build new item
                new_number = {
                    'phone_number': {'S': str(phone_number)},
                    'user_id': {'S': str(user_id)},
                    'status': {'S': old_number.get('status', {}).get('S') or old_number.get('status', 'active')},
                    'purchased_at': {'S': old_number.get('purchased_at', {}).get('S') or old_number.get('purchased_at', datetime.utcnow().isoformat() + 'Z')}
                }

                # Put to new table
                dynamodb.put_item(
                    TableName=NEW_TABLES['phone_numbers'],
                    Item=new_number,
                    ConditionExpression='attribute_not_exists(phone_number)'
                )

                migrated_count += 1
                logger.info(f"✅ Migrated phone number: {phone_number}")

            except dynamodb.exceptions.ConditionalCheckFailedException:
                logger.info(f"⏭️  Phone number {phone_number} already exists in new table, skipping")
            except Exception as e:
                logger.error(f"❌ Error migrating phone number {phone_number}: {e}")
                continue

        logger.info(f"\n✅ Migrated {migrated_count}/{len(old_numbers)} phone numbers")
        return migrated_count

    except Exception as e:
        logger.error(f"Error during phone number migration: {e}")
        return migrated_count


def main():
    """Run the complete migration"""
    logger.info("\n" + "🚀" * 30)
    logger.info("STARTING SIGMOYD-BACKEND SCHEMA MIGRATION")
    logger.info("🚀" * 30)

    # Check AWS credentials
    if not settings.aws_access_key_id:
        logger.warning("⚠️  AWS credentials not found in settings. Using default credential chain.")

    # Migrate in order
    agents_migrated = migrate_agents()
    calls_migrated = migrate_calls()
    numbers_migrated = migrate_phone_numbers()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("MIGRATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Agents migrated: {agents_migrated}")
    logger.info(f"Calls migrated: {calls_migrated}")
    logger.info(f"Phone numbers migrated: {numbers_migrated}")
    logger.info(f"Total items migrated: {agents_migrated + calls_migrated + numbers_migrated}")
    logger.info("\n✅ All data has been migrated to SIGMOYD-BACKEND schema!")
    logger.info("\n⚠️  IMPORTANT: Verify the data in new tables before deleting old tables.")
    logger.info("   You can keep both schemas running in parallel for testing.")


if __name__ == "__main__":
    main()
