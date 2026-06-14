
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.ad import Ad


def main():
    app = create_app()
    with app.app_context():
        # Delete any existing ads for StanD
        Ad.query.filter_by(user_whatsapp="+50942882076").delete()
        db.session.commit()
        print("Deleted existing ads for StanD")


if __name__ == "__main__":
    main()
