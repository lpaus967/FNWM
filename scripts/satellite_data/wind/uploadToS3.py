#!/usr/bin/env python3
"""
S3 Wind Data Uploader

Uploads processed HRRR wind GRIB files to AWS S3 bucket.
Supports uploading with metadata and optional cleanup of local files.
"""

import boto3
from pathlib import Path
from datetime import datetime
import logging
from botocore.exceptions import ClientError

import config
import utils

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class S3Uploader:
    """Handle S3 uploads and management for wind data."""

    def __init__(self, bucket_name=None, region=None, profile=None):
        """
        Initialize S3 uploader.

        Args:
            bucket_name: Name of the S3 bucket (default from config)
            region: AWS region (default from config)
            profile: AWS profile name (if None, uses default credentials)
        """
        self.bucket_name = bucket_name or config.S3_BUCKET_NAME
        self.region = region or config.S3_REGION

        # Initialize S3 client
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        self.s3_client = session.client('s3', region_name=self.region)

        logger.info(f"Initialized S3 uploader for bucket: {self.bucket_name}")

    def check_bucket_exists(self):
        """Check if the S3 bucket exists."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"✓ Bucket exists: {self.bucket_name}")
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.error(f"✗ Bucket does not exist: {self.bucket_name}")
            else:
                logger.error(f"✗ Error checking bucket: {e}")
            return False

    def upload_file(self, file_path, s3_key=None, metadata=None):
        """Upload a single file to S3."""
        file_path = Path(file_path)

        if not file_path.exists():
            logger.error(f"✗ File not found: {file_path}")
            return False

        s3_key = s3_key or file_path.name

        try:
            extra_args = {'Metadata': metadata} if metadata else {}
            file_size_str = utils.format_file_size(file_path.stat().st_size)

            logger.info(f"Uploading {file_path.name} ({file_size_str})...")

            self.s3_client.upload_file(
                str(file_path),
                self.bucket_name,
                s3_key,
                ExtraArgs=extra_args
            )

            logger.info(f"✓ Uploaded: {s3_key}")
            return True

        except ClientError as e:
            logger.error(f"✗ Error uploading {file_path.name}: {e}")
            return False

    def upload_directory(self, directory, s3_prefix='', pattern=None, metadata=None):
        """Upload all files matching a pattern from a directory to S3."""
        directory = Path(directory)
        pattern = pattern or config.PROCESSED_FILE_PATTERN

        if not directory.exists():
            logger.error(f"✗ Directory not found: {directory}")
            return {**utils.init_results_dict(), 'total': 0}

        # Find all matching files
        files = sorted(directory.glob(pattern))

        if not files:
            logger.warning(f"No files matching '{pattern}' found in {directory}")
            return {**utils.init_results_dict(), 'total': 0}

        logger.info(f"\nFound {len(files)} files to upload:")
        for f in files:
            logger.info(f"  - {f.name}")

        # Upload each file
        results = utils.init_results_dict()

        for file_path in files:
            s3_key = f"{s3_prefix}/{file_path.name}" if s3_prefix else file_path.name

            # Add timestamp to metadata
            upload_metadata = metadata.copy() if metadata else {}
            upload_metadata.update({
                'upload_time': datetime.utcnow().isoformat(),
                'original_filename': file_path.name
            })

            success = self.upload_file(file_path, s3_key, upload_metadata)
            results['success' if success else 'failed'] += 1

        results['total'] = len(files)
        utils.print_summary("Upload Summary", results, separator_width=60)

        return results

    def list_bucket_objects(self, prefix='', max_keys=100):
        """List objects in the S3 bucket."""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )

            if 'Contents' in response:
                objects = [obj['Key'] for obj in response['Contents']]
                logger.info(f"\nFound {len(objects)} objects in bucket:")
                for obj in objects:
                    logger.info(f"  - {obj}")
                return objects
            else:
                logger.info("No objects found in bucket")
                return []

        except ClientError as e:
            logger.error(f"✗ Error listing objects: {e}")
            return []

    def delete_old_objects(self, prefix='', days_old=None):
        """Delete objects older than specified number of days."""
        days_old = days_old or config.S3_RETENTION_DAYS

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )

            if 'Contents' not in response:
                logger.info("No objects to delete")
                return 0

            # Filter objects by age
            cutoff_date = datetime.utcnow().timestamp() - (days_old * 86400)
            old_objects = [
                {'Key': obj['Key']}
                for obj in response['Contents']
                if obj['LastModified'].timestamp() < cutoff_date
            ]

            if not old_objects:
                logger.info(f"No objects older than {days_old} days found")
                return 0

            # Delete old objects
            logger.info(f"\nDeleting {len(old_objects)} old objects...")
            delete_response = self.s3_client.delete_objects(
                Bucket=self.bucket_name,
                Delete={'Objects': old_objects}
            )

            deleted_count = len(delete_response.get('Deleted', []))
            logger.info(f"✓ Deleted {deleted_count} objects")
            return deleted_count

        except ClientError as e:
            logger.error(f"✗ Error deleting old objects: {e}")
            return 0

    def cleanup_local_directory(self, directory):
        """Delete all files in a local directory."""
        directory = Path(directory)

        if not directory.exists():
            logger.info(f"ℹ Directory does not exist: {directory}")
            return True

        if not directory.is_dir():
            logger.error(f"✗ Path is not a directory: {directory}")
            return False

        try:
            files = [f for f in directory.iterdir() if f.is_file()]

            if not files:
                logger.info(f"ℹ No files to delete in: {directory}")
                return True

            logger.info(f"\nCleaning up directory: {directory}")
            logger.info(f"  Found {len(files)} file(s) to delete...")

            deleted_count = sum(1 for f in files if self._delete_file(f))

            if deleted_count == len(files):
                logger.info(f"  ✓ Successfully deleted {deleted_count} file(s)")
                return True
            else:
                logger.warning(f"  ⚠ Deleted {deleted_count}/{len(files)} file(s)")
                return False

        except Exception as e:
            logger.error(f"✗ Error cleaning directory {directory}: {e}")
            return False

    @staticmethod
    def _delete_file(file_path):
        """Helper to delete a single file."""
        try:
            file_path.unlink()
            return True
        except Exception as e:
            logger.error(f"  ✗ Failed to delete {file_path.name}: {e}")
            return False


def main():
    """Main function to upload HRRR GRIB files to S3."""
    logger.info("S3 Wind Data Upload")
    logger.info("=" * 60)

    # Generate S3 prefix with current date
    now = datetime.utcnow()
    s3_prefix = config.S3_PREFIX_TEMPLATE.format(
        year=now.year,
        month=now.month,
        day=now.day
    )

    logger.info(f"Bucket: {config.S3_BUCKET_NAME}")
    logger.info(f"S3 Prefix: {s3_prefix}")
    logger.info(f"Local directory: {config.PROCESSED_DIR}")
    logger.info("")

    try:
        # Initialize uploader
        uploader = S3Uploader()

        # Check if bucket exists
        if not uploader.check_bucket_exists():
            logger.error("\n✗ Bucket does not exist. Please run Terraform to create it:")
            logger.error("  terraform apply")
            return

        # Step 1: Upload processed GRIB files
        logger.info("\nStep 1: Uploading processed GRIB files to S3...")
        results = uploader.upload_directory(
            directory=str(config.PROCESSED_DIR),
            s3_prefix=s3_prefix,
            metadata=config.S3_METADATA
        )

        if results['failed'] > 0:
            logger.warning(f"\n⚠ {results['failed']} files failed to upload")

        if results['success'] == 0:
            logger.error("\n✗ No files were uploaded successfully")
            return

        # Step 2: List uploaded objects
        logger.info("\nStep 2: Verifying uploaded files...")
        uploader.list_bucket_objects(prefix=s3_prefix, max_keys=50)

        # Step 3: Cleanup local files
        logger.info("\nStep 3: Cleaning up local files...")
        uploader.cleanup_local_directory(config.RAW_GRIB_DIR)
        uploader.cleanup_local_directory(config.PROCESSED_DIR)

        # Step 4: Delete old S3 objects
        logger.info("\nStep 4: Cleaning up old S3 objects...")
        uploader.delete_old_objects(prefix='hrrr/')

        logger.info("\n" + "=" * 60)
        logger.info("Upload process complete!")
        logger.info(f"Files are available in S3:")
        logger.info(f"  s3://{config.S3_BUCKET_NAME}/{s3_prefix}/")
        logger.info("=" * 60)

    except Exception as error:
        logger.error(f"Error during wind data upload: {error}")
        raise


if __name__ == "__main__":
    main()
