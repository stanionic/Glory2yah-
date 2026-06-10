from app import app, db, Course, Admin, bcrypt

def init_database():
    with app.app_context():
        # Create all tables
        db.create_all()

        # Add sample courses
        if Course.query.count() == 0:
            courses = [
                Course(
                    name="Cours de Mathématiques",
                    description="Apprenez les bases des mathématiques avec des exercices pratiques et des explications claires.",
                    duration="3 mois",
                    fee=2500.00
                ),
                Course(
                    name="Cours d'Anglais",
                    description="Maîtrisez l'anglais parlé et écrit avec des cours interactifs et des conversations pratiques.",
                    duration="4 mois",
                    fee=3000.00
                ),
                Course(
                    name="Cours d'Informatique",
                    description="Découvrez l'informatique moderne avec des cours sur la programmation, les réseaux et les bases de données.",
                    duration="6 mois",
                    fee=5000.00
                ),
                Course(
                    name="Cours de Français",
                    description="Perfectionnez votre français avec des cours adaptés à tous les niveaux.",
                    duration="3 mois",
                    fee=2000.00
                ),
                Course(
                    name="Cours de Sciences",
                    description="Explorez les sciences naturelles avec des expériences pratiques et des démonstrations.",
                    duration="4 mois",
                    fee=2800.00
                )
            ]

            for course in courses:
                db.session.add(course)

        # Create default admin
        if not Admin.query.filter_by(username='admin').first():
            hashed_password = bcrypt.generate_password_hash('admin123').decode('utf-8')
            admin = Admin(username='admin', password_hash=hashed_password)
            db.session.add(admin)

        db.session.commit()
        print("Base de données initialisée avec succès!")

if __name__ == '__main__':
    init_database()
