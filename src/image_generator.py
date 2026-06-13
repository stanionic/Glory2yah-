import os
from PIL import Image, ImageDraw, ImageFont, ImageOps
import textwrap

def generate_composite_image(ads, output_path, assets_folder='static/uploads'):
    """
    Generates a 1200x628 composite image from 5 ads.
    
    Args:
        ads: List of 5 Ad objects.
        output_path: Path to save the generated image.
        assets_folder: Folder containing ad images.
        
    Returns:
        Path to the generated image.
    """
    if len(ads) != 5:
        raise ValueError("Exactly 5 ads are required to generate the composite image.")

    # Canvas dimensions
    CANVAS_WIDTH = 1200
    CANVAS_HEIGHT = 628
    
    # Column dimensions
    COL_WIDTH = CANVAS_WIDTH // 5
    COL_HEIGHT = CANVAS_HEIGHT
    
    # Create canvas
    canvas = Image.new('RGB', (CANVAS_WIDTH, CANVAS_HEIGHT), color='#FFFFFF')
    draw = ImageDraw.Draw(canvas)
    
    # Load font (fallback to default if not found)
    # On Linux/Render, fonts are usually in /usr/share/fonts/truetype/dejavu/
    linux_font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font_path = linux_font if os.path.exists(linux_font) else "arial.ttf"
    
    try:
        if not os.path.exists(font_path) and font_path == "arial.ttf":
             # If on Windows/Local and font exists, this works; if not, raises IOError
             font = ImageFont.truetype("arial.ttf", 20)
        font = ImageFont.truetype(font_path, 20)
        caption_font = ImageFont.truetype(font_path, 16)
        price_font = ImageFont.truetype(font_path, 18)
    except IOError:
        font = ImageFont.load_default()
        caption_font = ImageFont.load_default()
        price_font = ImageFont.load_default()

    for i, ad in enumerate(ads):
        x_offset = i * COL_WIDTH
        
        # 1. Process Main Image
        img_filename = None
        if ad.media_type == 'images' and ad.images:
            img_filename = ad.images.split(',')[0].strip()
        elif ad.media_type == 'video' and ad.video:
            # For video, we might need a thumbnail. 
            # Assuming a placeholder or extracting frame is too complex for now,
            # we'll look for an image fallback or use a video icon placeholder.
            # Ideally, the system should have generated a thumbnail.
            # For now, let's try to find an image if video is present, or use a generic one.
            if ad.images:
                img_filename = ad.images.split(',')[0].strip()
        
        # Load image
        ad_img = None
        if img_filename:
            img_path = os.path.join(assets_folder, img_filename)
            if os.path.exists(img_path):
                try:
                    ad_img = Image.open(img_path).convert('RGBA')
                except Exception:
                    pass
        
        if ad_img:
            # Resize and crop to fill the top part of the column
            # Let's reserve bottom 150px for text
            IMG_HEIGHT = COL_HEIGHT - 150
            ad_img = ImageOps.fit(ad_img, (COL_WIDTH - 10, IMG_HEIGHT), method=Image.Resampling.LANCZOS)
            
            # Paste image with some padding
            canvas.paste(ad_img, (x_offset + 5, 5))
        else:
            # Placeholder if no image
            draw.rectangle([x_offset + 5, 5, x_offset + COL_WIDTH - 5, COL_HEIGHT - 150], fill='#EEEEEE')
            draw.text((x_offset + 50, 200), "No Image", fill='#999999', font=font)

        # 2. Add Text/Caption
        text_y = COL_HEIGHT - 140
        
        # Title/Caption (Truncated)
        caption = ad.title if ad.title else (ad.description[:20] + "..." if len(ad.description) > 20 else ad.description)
        # Wrap text
        lines = textwrap.wrap(caption, width=20) # Approx chars
        y_text = text_y
        for line in lines[:2]: # Max 2 lines
            draw.text((x_offset + 10, y_text), line, fill='#333333', font=font)
            y_text += 25
            
        # Price
        if ad.price_gkach:
            price_text = f"{ad.price_gkach} Gkach"
            draw.text((x_offset + 10, y_text + 10), price_text, fill='#E91E63', font=price_font)

        # 3. WhatsApp Badge (Simulated Button)
        btn_y = COL_HEIGHT - 40
        draw.rectangle([x_offset + 10, btn_y, x_offset + COL_WIDTH - 10, btn_y + 30], fill='#25D366')
        draw.text((x_offset + 35, btn_y + 5), "WhatsApp", fill='white', font=caption_font)
        
        # Draw separator line
        if i < 4:
            draw.line([x_offset + COL_WIDTH, 10, x_offset + COL_WIDTH, COL_HEIGHT - 10], fill='#DDDDDD', width=1)

    # Save
    canvas.save(output_path, quality=95)
    return output_path
