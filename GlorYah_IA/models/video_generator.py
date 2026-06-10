"""
Générateur de vidéos simplifié
Version améliorée avec animations plus sophistiquées
"""

import os
import uuid
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import cv2
from datetime import datetime
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoGenerator:
    def __init__(self):
        """Initialisation du générateur de vidéos"""
        self.output_dir = Path("static/generated/videos")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Video generator initialized")
    
    def generate(self, prompt, duration=3, fps=30):
        """Génération de vidéo"""
        try:
            frames = int(duration * fps)
            return self.create_animation(prompt, frames, fps)
        except Exception as e:
            logger.error(f"Video generation error: {e}")
            raise Exception(f"Erè nan jenere videyo a: {str(e)}")
    
    def create_animation(self, prompt, frames=90, fps=30):
        """Création d'une animation basée sur le prompt"""
        width, height = 1280, 720
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        filename = f"{uuid.uuid4().hex}.mp4"
        filepath = self.output_dir / filename
        
        out = cv2.VideoWriter(str(filepath), fourcc, fps, (width, height))
        
        try:
            logger.info(f"Creating video animation: {prompt[:50]}...")
            
            animation_type = self._detect_animation_type(prompt)
            
            for i in range(frames):
                frame = self._create_frame(
                    i, frames, width, height, prompt, animation_type
                )
                out.write(frame)
            
            out.release()
            
            file_size = filepath.stat().st_size
            duration = frames / fps
            
            logger.info(f"Video created: {filename} ({file_size} bytes, {duration}s)")
            
            return filename, str(filepath)
            
        except Exception as e:
            out.release()
            logger.error(f"Animation creation error: {e}")
            raise
    
    def _detect_animation_type(self, prompt):
        """Détecte le type d'animation à partir du prompt"""
        prompt_lower = prompt.lower()
        
        if any(word in prompt_lower for word in ['wave', 'vag', 'ocean', 'lanmè']):
            return 'wave'
        elif any(word in prompt_lower for word in ['circle', 'sèk', 'round', 'won']):
            return 'circles'
        elif any(word in prompt_lower for word in ['star', 'zetwal', 'étoile']):
            return 'stars'
        elif any(word in prompt_lower for word in ['gradient', 'color', 'koulè']):
            return 'gradient'
        else:
            return 'default'
    
    def _create_frame(self, frame_idx, total_frames, width, height, prompt, anim_type):
        """Crée une frame individuelle"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        progress = frame_idx / total_frames
        
        if anim_type == 'wave':
            frame = self._wave_animation(frame, progress, width, height)
        elif anim_type == 'circles':
            frame = self._circles_animation(frame, progress, width, height)
        elif anim_type == 'stars':
            frame = self._stars_animation(frame, progress, width, height)
        elif anim_type == 'gradient':
            frame = self._gradient_animation(frame, progress, width, height)
        else:
            frame = self._default_animation(frame, progress, width, height)
        
        self._add_text(frame, prompt, frame_idx, total_frames)
        
        return frame
    
    def _wave_animation(self, frame, progress, width, height):
        """Animation de vagues"""
        frame[:, :] = [139, 69, 19]
        
        for wave in range(5):
            y_offset = int(height * 0.3 + wave * 50)
            amplitude = 30 + wave * 10
            frequency = 0.01 + wave * 0.002
            phase = progress * 2 * np.pi + wave * 0.5
            
            for x in range(width):
                y = int(y_offset + amplitude * np.sin(frequency * x + phase))
                if 0 <= y < height:
                    color_intensity = 200 - wave * 30
                    cv2.circle(frame, (x, y), 3, (color_intensity, color_intensity, 255), -1)
        
        return frame
    
    def _circles_animation(self, frame, progress, width, height):
        """Animation de cercles concentriques"""
        frame[:, :] = [20, 20, 20]
        
        center_x, center_y = width // 2, height // 2
        
        for i in range(10):
            radius = int(50 + (i * 60 + progress * 500) % 500)
            alpha = 1.0 - (radius / 500)
            color_val = int(255 * alpha)
            
            color = (
                int(100 + 155 * np.sin(progress * 2 * np.pi + i)),
                int(100 + 155 * np.cos(progress * 2 * np.pi + i)),
                color_val
            )
            
            cv2.circle(frame, (center_x, center_y), radius, color, 3)
        
        return frame
    
    def _stars_animation(self, frame, progress, width, height):
        """Animation d'étoiles"""
        frame[:, :] = [10, 10, 30]
        
        np.random.seed(42)
        num_stars = 100
        
        for i in range(num_stars):
            x = int((i * 137.5) % width)
            y = int((i * 217.3) % height)
            
            brightness = int(128 + 127 * np.sin(progress * 2 * np.pi * 3 + i))
            size = 2 + int(3 * np.sin(progress * np.pi + i))
            
            cv2.circle(frame, (x, y), size, (brightness, brightness, 255), -1)
        
        return frame
    
    def _gradient_animation(self, frame, progress, width, height):
        """Animation de dégradé de couleurs"""
        for y in range(height):
            for x in range(width):
                r = int(128 + 127 * np.sin(progress * 2 * np.pi + x / width * np.pi))
                g = int(128 + 127 * np.sin(progress * 2 * np.pi + y / height * np.pi))
                b = int(128 + 127 * np.cos(progress * 2 * np.pi))
                
                frame[y, x] = [b, g, r]
        
        return frame
    
    def _default_animation(self, frame, progress, width, height):
        """Animation par défaut"""
        color_value = int(255 * progress)
        
        frame[:, :, 0] = color_value
        frame[:, :, 1] = 255 - color_value
        frame[:, :, 2] = 128
        
        center_x, center_y = width // 2, height // 2
        radius = 50 + int(30 * np.sin(progress * 2 * np.pi * 3))
        
        cv2.circle(frame, (center_x, center_y), radius, (255, 255, 255), -1)
        cv2.circle(frame, (center_x, center_y), radius + 10, (0, 0, 0), 3)
        
        return frame
    
    def _add_text(self, frame, prompt, frame_idx, total_frames):
        """Ajoute du texte sur la frame"""
        text = "MANDEMMAPBAW"
        font = cv2.FONT_HERSHEY_BOLD
        font_scale = 2
        thickness = 3
        
        (text_width, text_height), _ = cv2.getTextSize(text, font, font_scale, thickness)
        
        x = (frame.shape[1] - text_width) // 2
        y = 80
        
        cv2.putText(frame, text, (x + 3, y + 3), font, font_scale, (0, 0, 0), thickness + 2)
        cv2.putText(frame, text, (x, y), font, font_scale, (255, 255, 255), thickness)
        
        prompt_text = prompt[:60] + "..." if len(prompt) > 60 else prompt
        font_scale_small = 0.8
        thickness_small = 2
        
        (prompt_width, prompt_height), _ = cv2.getTextSize(
            prompt_text, font, font_scale_small, thickness_small
        )
        
        x_prompt = (frame.shape[1] - prompt_width) // 2
        y_prompt = frame.shape[0] - 60
        
        cv2.putText(
            frame, prompt_text, (x_prompt + 2, y_prompt + 2),
            font, font_scale_small, (0, 0, 0), thickness_small + 1
        )
        cv2.putText(
            frame, prompt_text, (x_prompt, y_prompt),
            font, font_scale_small, (255, 255, 255), thickness_small
        )
        
        progress = frame_idx / total_frames
        bar_width = int(frame.shape[1] * 0.8)
        bar_height = 10
        bar_x = (frame.shape[1] - bar_width) // 2
        bar_y = frame.shape[0] - 30
        
        cv2.rectangle(
            frame,
            (bar_x, bar_y),
            (bar_x + bar_width, bar_y + bar_height),
            (100, 100, 100),
            -1
        )
        
        progress_width = int(bar_width * progress)
        cv2.rectangle(
            frame,
            (bar_x, bar_y),
            (bar_x + progress_width, bar_y + bar_height),
            (0, 255, 0),
            -1
        )
    
    def is_available(self):
        """Vérifie si le générateur est disponible"""
        return True
