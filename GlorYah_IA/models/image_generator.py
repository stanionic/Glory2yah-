"""
Générateur d'images avec Stable Diffusion
Version améliorée avec gestion d'erreurs et optimisations
"""

# Optional imports - will fallback if not available
try:
    import torch
    from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    StableDiffusionPipeline = None
    DPMSolverMultistepScheduler = None

from PIL import Image, ImageDraw, ImageFont
import os
import uuid
from datetime import datetime
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageGenerator:
    def __init__(self, model_id="runwayml/stable-diffusion-v1-5"):
        """Initialisation du générateur d'images"""
        self.model_id = model_id
        self.device = None
        self.output_dir = Path("static/generated/images")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.pipe = None
        
        if not TORCH_AVAILABLE:
            logger.warning("Torch not available. Image generator will use fallback mode only.")
            return
        
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        try:
            self._load_model()
        except Exception as e:
            logger.error(f"Error loading image model: {e}")
            logger.info("Image generator will use fallback mode")
    
    def _load_model(self):
        """Chargement du modèle Stable Diffusion"""
        if not TORCH_AVAILABLE:
            raise ImportError("Torch is not available")
            
        try:
            logger.info(f"Loading Stable Diffusion model: {self.model_id}")
            
            # Special handling for Windows DLL errors
            try:
                self.pipe = StableDiffusionPipeline.from_pretrained(
                    self.model_id,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                    safety_checker=None,
                    requires_safety_checker=False
                )
            except OSError as e:
                if "DLL" in str(e) or "1114" in str(e):
                    # Windows DLL error - provide helpful message
                    logger.error(f"Windows DLL error detected: {e}")
                    logger.error("This is a common Windows issue with PyTorch.")
                    logger.error("Solutions:")
                    logger.error("1. Install Visual C++ Redistributables: https://aka.ms/vs/17/release/vc_redist.x64.exe")
                    logger.error("2. Or use Smart Fallback mode: pip uninstall torch -y && pip install -r requirements-basic.txt")
                    raise ImportError(f"Windows DLL error. Install Visual C++ Redistributables or use Smart Fallback mode. Error: {e}")
                raise
            
            if self.device == "cuda":
                self.pipe = self.pipe.to("cuda")
                try:
                    self.pipe.enable_xformers_memory_efficient_attention()
                    logger.info("xformers memory efficient attention enabled")
                except Exception:
                    logger.info("xformers not available, using standard attention")
            else:
                self.pipe = self.pipe.to("cpu")
                self.pipe.enable_attention_slicing()
            
            self.pipe.scheduler = DPMSolverMultistepScheduler.from_config(
                self.pipe.scheduler.config
            )
            
            logger.info("Image generator initialized successfully")
            
        except Exception as e:
            logger.error(f"Error loading image model: {e}")
            raise
    
    def generate(self, prompt, negative_prompt=None, num_inference_steps=None):
        """Génération d'image"""
        if not TORCH_AVAILABLE or not self.pipe:
            return self._generate_placeholder(prompt)
        
        try:
            if num_inference_steps is None:
                num_inference_steps = 25 if self.device == "cuda" else 15
            
            if negative_prompt is None:
                negative_prompt = "blurry, bad quality, distorted, ugly"
            
            logger.info(f"Generating image for prompt: {prompt[:50]}...")
            
            with torch.no_grad():
                image = self.pipe(
                    prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=7.5,
                    height=512,
                    width=512
                ).images[0]
            
            filename = f"{uuid.uuid4().hex}.png"
            filepath = self.output_dir / filename
            
            image.save(str(filepath), "PNG", optimize=True)
            
            file_size = filepath.stat().st_size
            
            logger.info(f"Image generated successfully: {filename} ({file_size} bytes)")
            
            return filename, str(filepath)
            
        except Exception as e:
            # Handle CUDA out of memory if torch is available
            if TORCH_AVAILABLE and torch and 'cuda' in str(type(e).__name__).lower() and 'memory' in str(e).lower():
                logger.error("CUDA out of memory, trying with reduced steps")
                if hasattr(torch, 'cuda'):
                    torch.cuda.empty_cache()
                return self.generate(prompt, negative_prompt, num_inference_steps=10)
            
            logger.error(f"Image generation error: {e}")
            return self._generate_placeholder(prompt)
    
    def _generate_placeholder(self, prompt):
        """Génère une image placeholder quand le modèle n'est pas disponible"""
        try:
            img = Image.new('RGB', (512, 512), color=(73, 109, 137))
            d = ImageDraw.Draw(img)
            
            text = f"MANDEMMAPBAW\n\nImage placeholder\n\n{prompt[:50]}..."
            
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
            except:
                font = ImageFont.load_default()
            
            bbox = d.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            position = ((512 - text_width) / 2, (512 - text_height) / 2)
            
            d.multiline_text(position, text, fill=(255, 255, 255), font=font, align='center')
            
            filename = f"placeholder_{uuid.uuid4().hex}.png"
            filepath = self.output_dir / filename
            img.save(str(filepath), "PNG")
            
            logger.info(f"Placeholder image created: {filename}")
            
            return filename, str(filepath)
            
        except Exception as e:
            logger.error(f"Error creating placeholder: {e}")
            raise Exception("Mwen pa kapab kreye imaj la. Sistèm nan pa disponib.")
    
    def is_available(self):
        """Vérifie si le générateur est disponible"""
        return self.pipe is not None
