"""
Script pour créer les causes caritatives par défaut
"""
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models.charity import CharityCause

app = create_app()

DEFAULT_CAUSES = [
    {
        'cause_id': 'general',
        'name': 'Jeneral',
        'description': 'Fond jeneral pou ede moun nan bezwen nan kominote a',
        'icon': '❤️'
    },
    {
        'cause_id': 'education',
        'name': 'Edikasyon',
        'description': 'Ede timoun ak jèn ki pa gen mwayen pou ale lekòl',
        'icon': '📚'
    },
    {
        'cause_id': 'health',
        'name': 'Sante',
        'description': 'Sipò pou swen sante moun ki nan bezwen',
        'icon': '🏥'
    },
    {
        'cause_id': 'community',
        'name': 'Kominote',
        'description': 'Pwojè kominotè pou devlope katye yo',
        'icon': '🏘️'
    },
    {
        'cause_id': 'food',
        'name': 'Manje',
        'description': 'Distribisyon manje pou moun ki grangou',
        'icon': '🍲'
    }
]


def seed_causes():
    """Create default charity causes"""
    with app.app_context():
        print("=" * 60)
        print("SEEDING CHARITY CAUSES")
        print("=" * 60)
        
        created = 0
        for cause_data in DEFAULT_CAUSES:
            existing = CharityCause.query.filter_by(cause_id=cause_data['cause_id']).first()
            if existing:
                print(f"  [SKIP] {cause_data['name']} - already exists")
                continue
            
            cause = CharityCause(
                cause_id=cause_data['cause_id'],
                name=cause_data['name'],
                description=cause_data['description'],
                icon=cause_data['icon'],
                is_active=True
            )
            db.session.add(cause)
            created += 1
            print(f"  [OK] {cause_data['name']} - {cause_data['icon']}")
        
        db.session.commit()
        print(f"\n{'=' * 60}")
        print(f"RESULT: {created} causes created")
        print(f"{'=' * 60}")
        
        return True


if __name__ == '__main__':
    success = seed_causes()
    if success:
        print("\n✅ Causes caritatives créées avec succès!")
    else:
        print("\n❌ Erreur lors de la création des causes")
