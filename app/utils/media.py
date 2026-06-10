"""
Media Utilities
GIF generation and video processing
"""
import os
from PIL import Image
from flask import current_app


def create_gif_from_images(image_paths, output_path, duration=1.0):
    """Create a GIF from a list of image paths"""
    try:
        images = []
        for img_path in image_paths:
            if os.path.exists(img_path):
                img = Image.open(img_path)
                # Resize to consistent size
                img = img.resize((500, 500), Image.Resampling.LANCZOS)
                images.append(img)
        
        if not images:
            return None

        # Save as GIF
        images[0].save(
            output_path, 
            save_all=True, 
            append_images=images[1:], 
            duration=int(duration * 1000), 
            loop=0
        )
        return output_path
    except Exception as e:
        current_app.logger.error(f"Error creating GIF: {str(e)}")
        return None


def generate_ad_gif(ad):
    """Generate a GIF for an ad if it has multiple images"""
    if ad.media_type != 'images':
        return None

    images_list = ad.get_images_list()
    if len(images_list) < 2:
        return None

    upload_folder = current_app.config['UPLOAD_FOLDER']
    image_paths = [os.path.join(upload_folder, img) for img in images_list]
    
    gif_filename = f"{ad.ad_id}_preview.gif"
    gif_path = os.path.join(upload_folder, gif_filename)

    if os.path.exists(gif_path):
        return gif_filename

    if create_gif_from_images(image_paths, gif_path):
        return gif_filename
    
    return None
