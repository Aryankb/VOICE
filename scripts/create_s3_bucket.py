"""
Script to create S3 bucket for recording storage

Usage:
    python scripts/create_s3_bucket.py
"""

import sys
import os
import boto3
from botocore.exceptions import ClientError

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings


def create_s3_bucket():
    """Create S3 bucket with encryption and versioning"""
    bucket_name = settings.s3_bucket_recordings
    region = settings.aws_region

    print("=" * 60)
    print("S3 Bucket Creation Script")
    print("=" * 60)
    print(f"Bucket Name: {bucket_name}")
    print(f"Region: {region}")
    print("=" * 60)

    # Create S3 client
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        s3_client = boto3.client(
            's3',
            region_name=region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key
        )
    else:
        s3_client = boto3.client('s3', region_name=region)

    try:
        # Create bucket
        print(f"\n✓ Creating bucket: {bucket_name}")

        if region == 'us-east-1':
            # us-east-1 doesn't need LocationConstraint
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': region}
            )

        print(f"✓ Bucket {bucket_name} created successfully!")

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'BucketAlreadyOwnedByYou':
            print(f"⚠ Bucket {bucket_name} already exists and is owned by you")
        elif error_code == 'BucketAlreadyExists':
            print(f"✗ Bucket {bucket_name} already exists (owned by someone else)")
            print("   Please choose a different bucket name in .env")
            return False
        else:
            print(f"✗ Error creating bucket: {e}")
            return False

    # Enable encryption
    print("\n✓ Enabling server-side encryption (AES256)")
    try:
        s3_client.put_bucket_encryption(
            Bucket=bucket_name,
            ServerSideEncryptionConfiguration={
                'Rules': [{
                    'ApplyServerSideEncryptionByDefault': {
                        'SSEAlgorithm': 'AES256'
                    },
                    'BucketKeyEnabled': True
                }]
            }
        )
        print("✓ Encryption enabled")
    except ClientError as e:
        print(f"⚠ Could not enable encryption: {e}")

    # Enable versioning (optional but recommended)
    print("\n✓ Enabling versioning")
    try:
        s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        print("✓ Versioning enabled")
    except ClientError as e:
        print(f"⚠ Could not enable versioning: {e}")

    # Set lifecycle policy to automatically archive old recordings
    print("\n✓ Setting lifecycle policy (transition to Glacier after 90 days)")
    try:
        s3_client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration={
                'Rules': [
                    {
                        'ID': 'ArchiveOldRecordings',  # Note: uppercase ID
                        'Status': 'Enabled',
                        'Filter': {'Prefix': settings.s3_recordings_prefix},
                        'Transitions': [
                            {
                                'Days': 90,
                                'StorageClass': 'GLACIER'
                            }
                        ]
                    }
                ]
            }
        )
        print("✓ Lifecycle policy set")
    except ClientError as e:
        print(f"⚠ Could not set lifecycle policy: {e}")

    # Add bucket tags
    print("\n✓ Adding bucket tags")
    try:
        s3_client.put_bucket_tagging(
            Bucket=bucket_name,
            Tagging={
                'TagSet': [
                    {'Key': 'Project', 'Value': 'VoiceAssistant'},
                    {'Key': 'Purpose', 'Value': 'CallRecordings'},
                    {'Key': 'Environment', 'Value': 'Production'}
                ]
            }
        )
        print("✓ Tags added")
    except ClientError as e:
        print(f"⚠ Could not add tags: {e}")

    # Verify bucket exists and is accessible
    print("\n✓ Verifying bucket access")
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print("✓ Bucket is accessible")
    except ClientError as e:
        print(f"✗ Bucket verification failed: {e}")
        return False

    print("\n" + "=" * 60)
    print("✓ S3 bucket setup complete!")
    print("=" * 60)
    print(f"\nBucket URL: s3://{bucket_name}")
    print(f"Recordings will be stored at: s3://{bucket_name}/{settings.s3_recordings_prefix}")
    print("\nNext steps:")
    print("  1. python scripts/seed_data.py  (create test agents)")
    print("  2. python app.py  (start the server)")
    print("=" * 60)

    return True


def main():
    """Main function"""
    if not settings.enable_s3_upload:
        print("⚠ S3 upload is disabled in settings.")
        print("  Set ENABLE_S3_UPLOAD=true in .env to enable it.")
        return 1

    success = create_s3_bucket()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
