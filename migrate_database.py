from app import app, db
from sqlalchemy import text

print("=" * 50)
print("DATABASE MIGRATION SCRIPT")
print("=" * 50)

with app.app_context():
    try:
        # Add missing columns to cart_items table
        print("\nAdding missing columns to cart_items table...")
        
        columns_to_add = [
            ("negotiation_status", "VARCHAR(20) DEFAULT 'cart'"),
            ("cart_id", "VARCHAR(36)"),
            ("delivery_address", "TEXT")
        ]
        
        for column_name, column_type in columns_to_add:
            try:
                db.session.execute(text(f"ALTER TABLE cart_items ADD COLUMN {column_name} {column_type}"))
                db.session.commit()
                print(f"  ✓ Added column: {column_name}")
            except Exception as e:
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"  - Column {column_name} already exists")
                else:
                    print(f"  ✗ Error adding {column_name}: {str(e)}")
                db.session.rollback()
        
        print("\n" + "=" * 50)
        print("MIGRATION COMPLETE")
        print("=" * 50)
        print("\nDatabase schema updated successfully!")
        
    except Exception as e:
        print(f"\n✗ Migration failed: {str(e)}")
        db.session.rollback()
