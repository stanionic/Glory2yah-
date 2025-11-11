#!/usr/bin/env python3
"""
Auto-publish approved batches to Facebook
This script automatically publishes all approved batches to the specified Facebook page.
"""

import os
import sys
from datetime import datetime

# Add current directory to path to import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from models import db, Batch, Ad
from src.facebook_publisher import facebook_publisher
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def auto_publish_approved_batches():
    """Automatically publish all approved batches to Facebook."""

    # Initialize Flask app context
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///glory2yahpub.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    with app.app_context():
        db.init_app(app)

        try:
            # Get all approved batches that haven't been published yet
            approved_batches = Batch.query.filter(
                Batch.ads.isnot(None),
                Batch.ads != ''
            ).all()

            if not approved_batches:
                logger.info("No approved batches found to publish.")
                return

            logger.info(f"Found {len(approved_batches)} approved batches to publish.")

            # Validate Facebook credentials
            success, message = facebook_publisher.validate_credentials()
            if not success:
                logger.error(f"Facebook credentials validation failed: {message}")
                return

            logger.info("Facebook credentials validated successfully.")

            # Get app URL for links
            app_url = os.environ.get('APP_URL', 'https://glory2yahpub.onrender.com')

            total_published = 0
            total_failed = 0

            for batch in approved_batches:
                try:
                    logger.info(f"Processing batch {batch.batch_id}...")

                    # Get ads in this batch
                    ad_ids = batch.ads.split(',')
                    ads = Ad.query.filter(
                        Ad.ad_id.in_(ad_ids),
                        Ad.admin_status == 'approved'
                    ).all()

                    if not ads:
                        logger.warning(f"No approved ads found in batch {batch.batch_id}")
                        continue

                    logger.info(f"Publishing {len(ads)} ads from batch {batch.batch_id}")

                    # Publish batch to Facebook
                    results = facebook_publisher.publish_batch_to_facebook(ads, app_url)

                    successful = len(results['successful'])
                    failed = len(results['failed'])

                    total_published += successful
                    total_failed += failed

                    if successful > 0:
                        logger.info(f"✅ Successfully published {successful} ads from batch {batch.batch_id}")
                        for result in results['successful']:
                            logger.info(f"  - {result['title']} (Post ID: {result['post_id']})")

                    if failed > 0:
                        logger.error(f"❌ Failed to publish {failed} ads from batch {batch.batch_id}")
                        for result in results['failed']:
                            logger.error(f"  - {result['title']}: {result['error']}")

                except Exception as e:
                    logger.error(f"Error processing batch {batch.batch_id}: {str(e)}")
                    total_failed += 1

            logger.info("Auto-publish completed!")
            logger.info(f"Total ads published: {total_published}")
            logger.info(f"Total ads failed: {total_failed}")

            if total_published > 0:
                logger.info("✅ Auto-publish completed successfully!")
            else:
                logger.warning("⚠️ No ads were published. Check Facebook credentials and batch status.")

        except Exception as e:
            logger.error(f"Critical error during auto-publish: {str(e)}")

if __name__ == "__main__":
    logger.info("Starting auto-publish of approved batches to Facebook...")
    auto_publish_approved_batches()
    logger.info("Auto-publish script finished.")
