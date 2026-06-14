
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User


def main():
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(whatsapp="+50942882076").first()
        if user:
            user.name = "StanD"
            db.session.commit()
            print(f"Updated user name to {user.name}")


if __name__ == "__main__":
    main()
