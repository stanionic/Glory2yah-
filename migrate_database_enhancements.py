"""
Database Migration Script for Glory2YahPub Enhancements
Adds new fields and indexes for:
- Delivery date management
- Gkach cashout system
- Performance optimization indexes
"""

from app import app, db
from models import Delivery, GkachCashoutRequest, Ad, UserGkach
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """Run all database migrations"""
    with app.app_context():
        logger.info("Starting database migration...")
        
        # Create all tables (including new GkachCashoutRequest)
        try:
            db.create_all()
            logger.info("✓ All tables created/verified")
        except Exception as e:
            logger.error(f"Error creating tables: {str(e)}")
            return False
        
        # Add new columns to Delivery table
        delivery_migrations = [
            ("delivered_at", "ALTER TABLE deliveries ADD COLUMN delivered_at DATETIME"),
            ("delivery_date", "ALTER TABLE deliveries ADD COLUMN delivery_date DATETIME"),
            ("delivery_date_set_at", "ALTER TABLE deliveries ADD COLUMN delivery_date_set_at DATETIME"),
            ("delivery_notes", "ALTER TABLE deliveries ADD COLUMN delivery_notes TEXT"),
        ]
        
        for column_name, sql in delivery_migrations:
            try:
                db.session.execute(text(sql))
                db.session.commit()
                logger.info(f"✓ Added column '{column_name}' to deliveries table")
            except Exception as e:
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    logger.info(f"  Column '{column_name}' already exists, skipping")
                    db.session.rollback()
                else:
                    logger.error(f"Error adding column '{column_name}': {str(e)}")
                    db.session.rollback()
        
        # Create indexes for performance optimization
        indexes = [
            # Ad indexes
            ("idx_ad_status", "CREATE INDEX IF NOT EXISTS idx_ad_status ON ads(admin_status)"),
            ("idx_ad_batch", "CREATE INDEX IF NOT EXISTS idx_ad_batch ON ads(batch_id)"),
            ("idx_ad_user", "CREATE INDEX IF NOT EXISTS idx_ad_user ON ads(user_whatsapp)"),
            ("idx_ad_created", "CREATE INDEX IF NOT EXISTS idx_ad_created ON ads(created_at)"),
            ("idx_ad_type", "CREATE INDEX IF NOT EXISTS idx_ad_type ON ads(ad_type)"),
            
            # Delivery indexes
            ("idx_delivery_buyer", "CREATE INDEX IF NOT EXISTS idx_delivery_buyer ON deliveries(buyer_whatsapp)"),
            ("idx_delivery_seller", "CREATE INDEX IF NOT EXISTS idx_delivery_seller ON deliveries(seller_whatsapp)"),
            ("idx_delivery_status", "CREATE INDEX IF NOT EXISTS idx_delivery_status ON deliveries(status)"),
            ("idx_delivery_created", "CREATE INDEX IF NOT EXISTS idx_delivery_created ON deliveries(created_at)"),
            
            # UserGkach indexes
            ("idx_user_whatsapp", "CREATE INDEX IF NOT EXISTS idx_user_whatsapp ON user_gkach(user_whatsapp)"),
            
            # GkachCashoutRequest indexes
            ("idx_cashout_user", "CREATE INDEX IF NOT EXISTS idx_cashout_user ON gkach_cashout_requests(user_whatsapp)"),
            ("idx_cashout_status", "CREATE INDEX IF NOT EXISTS idx_cashout_status ON gkach_cashout_requests(status)"),
            ("idx_cashout_created", "CREATE INDEX IF NOT EXISTS idx_cashout_created ON gkach_cashout_requests(created_at)"),
        ]
        
        for index_name, sql in indexes:
            try:
                db.session.execute(text(sql))
                db.session.commit()
                logger.info(f"✓ Created index '{index_name}'")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    logger.info(f"  Index '{index_name}' already exists, skipping")
                    db.session.rollback()
                else:
                    logger.error(f"Error creating index '{index_name}': {str(e)}")
                    db.session.rollback()
        
        logger.info("✓ Database migration completed successfully!")
        return True

def verify_migration():
    """Verify that all migrations were applied correctly"""
    with app.app_context():
        logger.info("\nVerifying migration...")
        
        # Check if new columns exist in Delivery table
        try:
            result = db.session.execute(text("PRAGMA table_info(deliveries)"))
            columns = [row[1] for row in result]
            
            required_columns = ['delivered_at', 'delivery_date', 'delivery_date_set_at', 'delivery_notes']
            for col in required_columns:
                if col in columns:
                    logger.info(f"✓ Column '{col}' exists in deliveries table")
                else:
                    logger.warning(f"✗ Column '{col}' NOT found in deliveries table")
        except Exception as e:
            logger.error(f"Error verifying columns: {str(e)}")
        
        # Check if GkachCashoutRequest table exists
        try:
            result = db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='gkach_cashout_requests'"))
            if result.fetchone():
                logger.info("✓ Table 'gkach_cashout_requests' exists")
            else:
                logger.warning("✗ Table 'gkach_cashout_requests' NOT found")
        except Exception as e:
            logger.error(f"Error verifying table: {str(e)}")
        
        # Check indexes
        try:
            result = db.session.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))
            indexes = [row[0] for row in result]
            
            required_indexes = [
                'idx_ad_status', 'idx_ad_batch', 'idx_ad_user', 'idx_ad_created', 'idx_ad_type',
                'idx_delivery_buyer', 'idx_delivery_seller', 'idx_delivery_status', 'idx_delivery_created',
                'idx_user_whatsapp', 'idx_cashout_user', 'idx_cashout_status', 'idx_cashout_created'
            ]
            
            for idx in required_indexes:
                if idx in indexes:
                    logger.info(f"✓ Index '{idx}' exists")
                else:
                    logger.warning(f"✗ Index '{idx}' NOT found")
        except Exception as e:
            logger.error(f"Error verifying indexes: {str(e)}")
        
        logger.info("\nVerification complete!")

if __name__ == '__main__':
    print("=" * 60)
    print("Glory2YahPub Database Migration")
    print("=" * 60)
    print("\nThis script will:")
    print("1. Create new tables (GkachCashoutRequest)")
    print("2. Add new columns to Delivery table")
    print("3. Create performance indexes")
    print("\nStarting migration...\n")
    
    success = migrate_database()
    
    if success:
        print("\n" + "=" * 60)
        verify_migration()
        print("=" * 60)
        print("\n✓ Migration completed successfully!")
        print("\nYou can now run the application with the new features.")
    else:
        print("\n✗ Migration failed. Please check the errors above.")
