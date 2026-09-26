from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()


def use_external_db(external_db):
	"""Allow the module to share a host application's SQLAlchemy instance."""
	global db
	db = external_db
