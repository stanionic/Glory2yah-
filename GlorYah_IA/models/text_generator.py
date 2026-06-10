"""
Générateur de texte avec modèle local
Version améliorée avec cache et gestion d'erreurs
"""

import logging
from functools import lru_cache

# Optional imports - will fallback if not available
try:
    import torch
    from transformers import pipeline, AutoModelForCausalLM, AutoTokenizer
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    pipeline = None
    AutoModelForCausalLM = None
    AutoTokenizer = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextGenerator:
    def __init__(self, model_name="microsoft/phi-2"):
        """Initialisation du générateur de texte"""
        self.model_name = model_name
        self.device = None
        self.generator = None
        self.tokenizer = None
        self.model = None
        
        if not TORCH_AVAILABLE:
            logger.warning("Torch not available. Text generator will use fallback mode only.")
            return
        
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device: {self.device}")
        
        try:
            self._load_model()
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            logger.info("Text generator will use fallback mode")
    
    def _load_model(self):
        """Chargement du modèle"""
        if not TORCH_AVAILABLE:
            raise ImportError("Torch is not available")
            
        try:
            # Chargement du modèle et tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True
            )
            
            # Ajout du pad_token si nécessaire
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=torch.float32 if self.device == "cpu" else torch.float16,
                trust_remote_code=True,
                low_cpu_mem_usage=True
            )
            
            # Déplacer vers le device approprié
            if self.device == "cuda":
                self.model = self.model.to("cuda")
            
            # Création du pipeline
            self.generator = pipeline(
                "text-generation",
                model=self.model,
                tokenizer=self.tokenizer,
                device=0 if self.device == "cuda" else -1
            )
            
            logger.info(f"Text generator initialized successfully with {self.model_name}")
            
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            raise
    
    def generate(self, prompt, max_length=300, temperature=0.7, use_web_search=True):
        """Génération de texte avec support de recherche web"""
        if not self.generator:
            return self._fallback_response(prompt, use_web_search)
        
        try:
            # Nettoyage du prompt
            prompt = prompt.strip()
            
            # Formatage du prompt pour le modèle
            formatted_prompt = self._format_prompt(prompt)
            
            # Génération
            result = self.generator(
                formatted_prompt,
                max_length=max_length,
                do_sample=True,
                temperature=temperature,
                top_p=0.9,
                top_k=50,
                num_return_sequences=1,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                repetition_penalty=1.2
            )
            
            # Extraction de la réponse
            generated_text = result[0]['generated_text']
            response = self._extract_response(generated_text, formatted_prompt)
            
            return response if response else "Mwen pa gen repons pou kesyon sa a."
            
        except Exception as e:
            logger.error(f"Generation error: {e}")
            return self._fallback_response(prompt)
    
    def _format_prompt(self, prompt):
        """Formatage du prompt pour le modèle"""
        formatted = f"""Kòmandman: {prompt}

Repons:"""
        return formatted
    
    def _extract_response(self, generated_text, original_prompt):
        """Extraction de la réponse du texte généré"""
        try:
            # Enlever le prompt original
            if "Repons:" in generated_text:
                response = generated_text.split("Repons:")[-1].strip()
            else:
                response = generated_text.replace(original_prompt, "").strip()
            
            # Nettoyage
            response = response.split("\n\n")[0]
            response = response.strip()
            
            return response
            
        except Exception as e:
            logger.error(f"Response extraction error: {e}")
            return generated_text
    
    def _fallback_response(self, prompt, use_web_search=True):
        """Réponse de secours quand le modèle n'est pas disponible"""
        # Use smart fallback system instead of basic responses
        try:
            from .smart_fallback import get_smart_fallback
            fallback = get_smart_fallback()
            return fallback.generate(prompt, use_web_search=use_web_search)
        except Exception as e:
            logger.error(f"Smart fallback error: {e}")
            # Ultimate fallback
            return "Mwen la pou ede w! Bay m plis detay sou sa ou bezwen, tanpri."
    
    def is_available(self):
        """Vérifie si le générateur est disponible"""
        return self.generator is not None
