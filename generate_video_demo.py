#!/usr/bin/env python3
"""
Glory2YahPub Marketing Video Generator
Creates a short demo video in Haitian Creole showcasing the app's features.
"""

import os
import sys
from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import textwrap

class Glory2YahPubVideoGenerator:
    def __init__(self):
        self.width = 1080
        self.height = 1920  # Vertical video for social media
        self.fps = 30
        self.duration_per_slide = 4  # seconds

        # Colors
        self.primary_color = "#FFD700"  # Gold
        self.secondary_color = "#000000"  # Black
        self.text_color = "#FFFFFF"  # White

        # Font paths (will use default if not found)
        self.font_path = None
        try:
            # Try to find a suitable font
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/System/Library/Fonts/Arial.ttf",
                "/Library/Fonts/Arial.ttf",
                "C:/Windows/Fonts/arial.ttf"
            ]
            for path in font_paths:
                if os.path.exists(path):
                    self.font_path = path
                    break
        except:
            pass

    def create_text_clip(self, text, fontsize=80, color=None, duration=None):
        """Create a text clip with background"""
        if color is None:
            color = self.text_color

        if duration is None:
            duration = self.duration_per_slide

        # Create background
        bg = ColorClip(size=(self.width, self.height), color=self.secondary_color, duration=duration)

        # Create text clip
        txt_clip = TextClip(
            text,
            fontsize=fontsize,
            color=color,
            font=self.font_path,
            method='caption',
            size=(self.width-100, None),
            align='center'
        ).set_position('center').set_duration(duration)

        return CompositeVideoClip([bg, txt_clip])

    def create_slide_with_image(self, text, image_path=None, duration=None):
        """Create a slide with text and optional image"""
        if duration is None:
            duration = self.duration_per_slide

        # Background
        bg = ColorClip(size=(self.width, self.height), color=self.secondary_color, duration=duration)

        clips = [bg]

        # Add image if provided
        if image_path and os.path.exists(image_path):
            try:
                img_clip = ImageClip(image_path).resize(height=self.height//2).set_position(('center', 200)).set_duration(duration)
                clips.append(img_clip)
            except Exception as e:
                print(f"Warning: Could not load image {image_path}: {e}")

        # Add text
        txt_clip = TextClip(
            text,
            fontsize=60,
            color=self.primary_color,
            font=self.font_path,
            method='caption',
            size=(self.width-100, None),
            align='center'
        ).set_position(('center', self.height-300)).set_duration(duration)

        clips.append(txt_clip)

        return CompositeVideoClip(clips)

    def generate_demo_video(self, output_path="glory2yahpub_demo.mp4"):
        """Generate the complete demo video"""

        print("🚀 Generating Glory2YahPub Demo Video...")

        slides = []

        # Slide 1: Introduction
        slides.append(self.create_text_clip(
            "Byenveni nan Glory2YahPub!\n\n📱 Aplikasyon Piblisite #1 nan Ayiti",
            fontsize=70
        ))

        # Slide 2: What is Glory2YahPub?
        slides.append(self.create_text_clip(
            "Ki sa Glory2YahPub ye?\n\n🏪 Platfòm pou vandè ak achtè\n💰 Peye ak Gkach (Lajan Virtual)\n📢 Piblisite sou Facebook & Instagram",
            fontsize=60
        ))

        # Slide 3: For Sellers
        slides.append(self.create_text_clip(
            "Pou Vandè:\n\n📸 Telechaje foto piblisite w\n💰 Mete pri nan Gkach\n📤 Piblisite w ap parèt sou rezo sosyal\n💳 Resevwa pèman lè achtè achte",
            fontsize=55
        ))

        # Slide 4: For Buyers
        slides.append(self.create_text_clip(
            "Pou Achtè:\n\n🛒 Navige piblisite\n💳 Achte ak Gkach\n📍 Mande detay livrezon\n📱 Komunike ak vandè pa WhatsApp",
            fontsize=55
        ))

        # Slide 5: Gkach System
        slides.append(self.create_text_clip(
            "Sistèm Gkach:\n\n💰 1 Gkach = ~50 HTG\n🏦 Achte Gkach fasil\n📊 Suivi balans ou\n🔄 Transfè ant itilizatè",
            fontsize=55
        ))

        # Slide 6: How to Post Ad
        slides.append(self.create_text_clip(
            "Kouman Pibliye Piblisite:\n\n1️⃣ Telechaje 3 foto\n2️⃣ Ekri deskripsyon\n3️⃣ Mete pri\n4️⃣ Telechaje prèv pèman\n5️⃣ Administratè ap apwouve",
            fontsize=50
        ))

        # Slide 7: How to Buy
        slides.append(self.create_text_clip(
            "Kouman Achte:\n\n1️⃣ Chwazi piblisite\n2️⃣ Ajoute nan panier\n3️⃣ Mete adrès livrezon\n4️⃣ Vandè ap mete pri livrezon\n5️⃣ Peye ak Gkach\n6️⃣ Resevwa livrezon",
            fontsize=50
        ))

        # Slide 8: Communication
        slides.append(self.create_text_clip(
            "Komunikasyon:\n\n💬 WhatsApp entegre\n📞 Kontakte vandè dirèkteman\n📍 Suivi livrezon\n✅ Konfime resepsyon",
            fontsize=55
        ))

        # Slide 9: Admin Features
        slides.append(self.create_text_clip(
            "Fonksyon Administratè:\n\n✅ Apwouve piblisite\n💰 Jere balans Gkach\n📊 Rapò ak estatistik\n📱 Pibliye sou rezo sosyal",
            fontsize=55
        ))

        # Slide 10: Benefits
        slides.append(self.create_text_clip(
            "Benefis:\n\n🚀 Piblisite rapid\n💰 Pri abòdab\n📈 Ogmante lavant\n🌟 Komodite maksimòm",
            fontsize=60
        ))

        # Slide 11: Call to Action
        slides.append(self.create_text_clip(
            "Komanse Koulye a!\n\n📱 Telechaje aplikasyon an\n🏪 Kreye kont ou\n💰 Achte Gkach\n📢 Pibliye premye piblisite w\n\n#Glory2YahPub #Ayiti #Biznis",
            fontsize=55
        ))

        # Concatenate all slides
        print(f"📹 Creating video with {len(slides)} slides...")
        video = concatenate_videoclips(slides, method="compose")

        # Add background music (optional - would need to add audio file)
        # if os.path.exists("background_music.mp3"):
        #     audio = AudioFileClip("background_music.mp3").set_duration(video.duration)
        #     video = video.set_audio(audio)

        # Export video
        print(f"💾 Exporting video to {output_path}...")
        video.write_videofile(
            output_path,
            fps=self.fps,
            codec="libx264",
            audio_codec="aac",
            bitrate="8000k",
            preset="medium"
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
        print(f"📊 Size: {os.path.getsize(output_file) / (1024*1024):.1f} MB")

    except Exception as e:
        print(f"❌ Error generating video: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
