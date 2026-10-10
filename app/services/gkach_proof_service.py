"""Private storage for GKach payment proofs."""
import os
import uuid

from flask import current_app

from app.utils.validators import validate_file_upload


def gkach_proof_directory():
    """Return the non-static, persistent directory used for GKach proofs."""
    instance_dir = current_app.config.get('INSTANCE_DIR') or current_app.instance_path
    path = os.path.join(instance_dir, 'gkach_proofs')
    os.makedirs(path, exist_ok=True)
    return path


def save_gkach_proof(file_storage, max_size_mb=10):
    """Validate and save an image/PDF proof outside the public static tree."""
    allowed = (
        set(current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'}))
        | set(current_app.config.get('ALLOWED_DOCUMENT_EXTENSIONS', {'pdf'}))
    )
    validate_file_upload(file_storage, allowed, max_size_mb=max_size_mb)
    extension = file_storage.filename.rsplit('.', 1)[1].lower()
    filename = f'gkach_req_{uuid.uuid4().hex}.{extension}'
    file_storage.save(os.path.join(gkach_proof_directory(), filename))
    return filename
