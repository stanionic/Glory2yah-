#!/usr/bin/env python3
"""
Glory2YahPub Marketing Video Generator (Simplified Version)
Creates a short demo video in Haitian Creole showcasing the app's features.
Uses PIL for image generation instead of MoviePy text rendering.
"""

import os
import sys
from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont
import numpy as np

class Glory2YahPubVideoGenerator:
    def __init__(self):
        self.width = 1080
        self.height = 1920  # Vertical video for social media
        self.fps = 24
        self.duration_per_slide = 4  # seconds

        # Colors
        self.primary_color = "#FFD700"  # Gold
        self.secondary_color = "#000000"  # Black
        self.text_color = "#FFFFFF"  # White

        # Font - try to find a suitable font
        self.font_path = None
        try:
            font_paths = [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/calibri.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            ]
            for path in font_paths:
                if os.path.exists(path):
                    self.font_path = path
                    break
        except:
            pass

    def create_text_image(self, text, fontsize=80):
        """Create a PIL image with text"""
        # Create image
        img = Image.new('RGB', (self.width, self.height), color=self.secondary_color)
        draw = ImageDraw.Draw(img)

        # Load font
        try:
            if self.font_path:
                font = ImageFont.truetype(self.font_path, fontsize)
            else:
                font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()

        # Wrap text
        lines = []
        words = text.split()
        current_line = ""
        for word in words:
            test_line = current_line + " " + word if current_line else word
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] < self.width - 100:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)

        # Calculate text position
        total_text_height = len(lines) * (fontsize + 10)
        y_start = (self.height - total_text_height) // 2

        # Draw text
        y = y_start
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            x = (self.width - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, fill=self.primary_color, font=font)
            y += fontsize + 10

        return np.array(img)

    def create_text_clip(self, text, fontsize=80, duration=None):
        """Create a text clip from PIL image"""
        if duration is None:
            duration = self.duration_per_slide

        # Create image array
        img_array = self.create_text_image(text, fontsize)

        # Create video clip from image
        clip = ImageClip(img_array, duration=duration)
        return clip

    def generate_demo_video(self, output_path="glory2yahpub_demo.mp4"):
        """Generate the complete demo video"""

        print("🚀 Generating Glory2YahPub Demo Video...")

        slides = []

        # Slide 1: Introduction
        slides.append(self.create_text_clip(
            "Byenveni nan Glory2YahPub!\n\nAplikasyon Piblisite #1 nan Ayiti",
            fontsize=70
        ))

        # Slide 2: What is Glory2YahPub?
        slides.append(self.create_text_clip(
            "Ki sa Glory2YahPub ye?\n\nPlatfom pou vande ak achte\nPeye ak Gkach (Lajan Virtual)\nPiblisite sou Facebook & Instagram",
            fontsize=60
        ))

        # Slide 3: For Sellers
        slides.append(self.create_text_clip(
            "Pou Vande:\n\nTelechaje foto piblisite w\nMete pri nan Gkach\nPiblisite w ap parèt sou rezo sosyal\nResevwa peman lè achte achte",
            fontsize=55
        ))

        # Slide 4: For Buyers
        slides.append(self.create_text_clip(
            "Pou Achte:\n\nNavige piblisite\nAchète ak Gkach\nMande detay livrezon\nKomunike ak vande pa WhatsApp",
            fontsize=55
        ))

        # Slide 5: Gkach System
        slides.append(self.create_text_clip(
            "Sistem Gkach:\n\n1 Gkach = ~50 HTG\nAchète Gkach fasil\nSuivi balans ou\nTransfe ant itilizatè",
            fontsize=55
        ))

        # Slide 6: How to Post Ad
        slides.append(self.create_text_clip(
            "Kouman Pibliye Piblisite:\n\n1. Telechaje 3 foto\n2. Ekri deskripsyon\n3. Mete pri\n4. Telechaje prev peman\n5. Administrate ap apwouve",
            fontsize=50
        ))

        # Slide 7: How to Buy
        slides.append(self.create_text_clip(
            "Kouman Achte:\n\n1. Chwazi piblisite\n2. Ajoute nan panier\n3. Mete adres livrezon\n4. Vande ap mete pri livrezon\n5. Peye ak Gkach\n6. Resevwa livrezon",
            fontsize=50
        ))

        # Slide 8: Communication
        slides.append(self.create_text_clip(
            "Komunikasyon:\n\nWhatsApp entegre\nKontakte vande dirèkteman\nSuivi livrezon\nKonfime resepsyon",
            fontsize=55
        ))

        # Slide 9: Admin Features
        slides.append(self.create_text_clip(
            "Fonksyon Administrate:\n\nApwouve piblisite\nJere balans Gkach\nRapò ak estatistik\nPibliye sou rezo sosyal",
            fontsize=55
        ))

        # Slide 10: Benefits
        slides.append(self.create_text_clip(
            "Benefis:\n\nPiblisite rapid\nPri abordab\nOgmante lavant\nKomodite maksimom",
            fontsize=60
        ))

        # Slide 11: Call to Action
        slides.append(self.create_text_clip(
            "Komanse Koulye a!\n\nTelechaje aplikasyon an\nKreye kont ou\nAchète Gkach\nPibliye premye piblisite w\n\n#Glory2YahPub #Ayiti #Biznis",
            fontsize=55
        ))

        # Concatenate all slides
        print(f"📹 Creating video with {len(slides)} slides...")
        video = concatenate_videoclips(slides, method="compose")

        # Export video
        print(f"💾 Exporting video to {output_path}...")
        video.write_videofile(
            output_path,
            fps=self.fps,
            codec="libx264",
            audio=False,  # No audio to avoid issues
            bitrate="4000k",
            preset="fast"
        )

        print(f"✅ Video generated successfully: {output_path}")
        print(f"📏 Duration: {video.duration:.1f} seconds")
        print(f"📐 Resolution: {self.width}x{self.height}")

        return output_path

def main():
    generator = Glory2YahPubVideoGenerator()

    # Generate video
    output_file = "glory2yahpub_demo.mp4"
    try:
        generator.generate_demo_video(output_file)
        print(f"\n🎉 Demo video created successfully!")
        print(f"📁 File: {os.path.abspath(output_file)}")
        if os.path.exists(output_file):
            print(f"📊 Size: {os.path.getsize(output_file) / (1024*1024):.1f} MB")

    except Exception as e:
        print(f"❌ Error generating video: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
