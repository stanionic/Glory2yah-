"""
Smart Fallback System - AI-like responses without requiring torch
Uses pattern matching, templates, and NLP-like logic
"""

import re
import random
from datetime import datetime

class SmartFallback:
    """Intelligent fallback system that mimics AI behavior"""
    
    def __init__(self):
        self.patterns = self._load_patterns()
        self.context = []  # Simple conversation memory
        self.user_training = []  # User-submitted training examples
        self._load_user_training()
    
    def _load_user_training(self):
        """Load approved user training examples"""
        try:
            # Import here to avoid circular imports
            from database.training_models import TrainingConversation
            from database.models import db
            
            # Get approved conversations
            conversations = TrainingConversation.query.filter_by(
                approved=True
            ).order_by(TrainingConversation.used_count.asc()).limit(100).all()
            
            self.user_training = [
                {
                    'user_message': conv.user_message.lower(),
                    'response': conv.expected_response,
                    'category': conv.category,
                    'id': conv.id
                }
                for conv in conversations
            ]
            
            if self.user_training:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Loaded {len(self.user_training)} user training examples")
                
        except Exception as e:
            # If training tables don't exist yet, that's OK
            pass
        
    def _load_patterns(self):
        """Load response patterns for different types of input"""
        return {
            # Greetings
            'greetings': {
                'patterns': [
                    r'\b(bonjou|bonjour|hello|hi|salut|alo)\b',
                    r'\b(kijan ou ye|ki jan ou ye|comment ça va|how are you)\b',
                ],
                'responses': [
                    "Bonjou! Mwen byen, mèsi. Mwen se MANDEMMAPBAW, asistan AI ou a. Kisa mwen ka ede w jodi a?",
                    "Alo! Mwen la pou ede w. Ki kesyon ou genyen?",
                    "Bonjou! Mwen kontan wè w. Kòman mwen ka asiste w?",
                ]
            },
            
            # Questions about MANDEMMAPBAW
            'about_app': {
                'patterns': [
                    r'\b(ki sa|kisa|what|qu\'?est-ce).*\b(mandemmapbaw|app|aplikasyon)\b',
                    r'\b(ki moun|who).*\b(ou ye|you are)\b',
                    r'\b(eksplike|explain|tell me)\b',
                ],
                'responses': [
                    "MANDEMMAPBAW se yon asistan AI multimodal ki kreye pou Ayiti. Mwen ka:\n- Pale ak ou an Kreyòl ak Franse\n- Kreye imaj\n- Fè videyo\n- Jenere kòd\nKisa ou ta renmen eseye?",
                    "Mwen se MANDEMMAPBAW ('Mande m map baw' - Poze m kesyon, map ede w). Mwen se yon chatbot AI ki fèt pou ede moun pale Kreyòl. Mwen ka diskite, kreye imaj, videyo, ak kòd pou ou.",
                ]
            },
            
            # Help requests
            'help': {
                'patterns': [
                    r'\b(ede|help|aide|asiste)\b',
                    r'\b(ka fè|can do|peux faire)\b',
                    r'\b(fonksyon|features|capabilities)\b',
                ],
                'responses': [
                    "Mwen ka ede w ak plizyè bagay:\n\n1. 💬 Diskisyon - Pale avè m an Kreyòl oswa Franse\n2. 🖼️ Imaj - Kreye imaj selon deskripsyon ou\n3. 🎬 Videyo - Fè animasyon ak videyo\n4. 💻 Kòd - Jenere kòd pou pwojè ou yo\n\nKi youn ou ta renmen eseye?",
                    "Fonksyonalite MANDEMMAPBAW:\n- Chat entelijan an Kreyòl/Franse\n- Jenerasyon imaj (Stable Diffusion)\n- Kreyasyon videyo (4 estil animasyon)\n- Jenerasyon kòd (Python, JS, HTML, etc.)\n\nKisa ou bezwen?",
                ]
            },
            
            # Thanks
            'thanks': {
                'patterns': [
                    r'\b(mèsi|merci|thanks|thank you)\b',
                ],
                'responses': [
                    "Pa gen pwoblèm! Mwen la pou ede w nenpòt lè.",
                    "Ou mèt! Si ou gen lòt kesyon, pa ezite.",
                    "Mwen kontan mwen te kapab ede. Kontinye poze kesyon!",
                ]
            },
            
            # How questions
            'how_to': {
                'patterns': [
                    r'\b(kijan|kouman|comment|how).*\b(fè|make|do|create)\b',
                ],
                'responses': [
                    "Pou fè sa, ou ka:\n1. Dekri sa ou vle an detay\n2. Eksplike objektif ou a\n3. Mwen pral bay ou konsèy ak direksyon\n\nKi pwojè espesifik ou gen nan tèt ou?",
                ]
            },
            
            # Programming questions
            'programming': {
                'patterns': [
                    r'\b(python|javascript|code|kòd|program|pwogram)\b',
                    r'\b(function|class|variable|fonksyon)\b',
                ],
                'responses': [
                    "Mwen ka ede w ak pwogramasyon! Mwen sipòte:\n- Python\n- JavaScript\n- HTML/CSS\n- SQL\n- Java\n- C++\n\nKi kalite kòd ou bezwen? Bay m plis detay sou sa ou vle kreye.",
                ]
            },
            
            # Haiti-related
            'haiti': {
                'patterns': [
                    r'\b(ayiti|haiti|haïti|kreyòl|creole)\b',
                ],
                'responses': [
                    "Ayiti se peyi kote Kreyòl soti! Mwen fyè pou sèvi kominote ayisyen an. Kisa ou ta renmen konnen sou Ayiti oswa Kreyòl?",
                    "Kreyòl Ayisyen se yon lang bèl ak rich. Mwen la pou ede tout moun ki pale li. Kòman mwen ka ede w jodi a?",
                ]
            },
            
            # Image generation
            'image': {
                'patterns': [
                    r'\b(imaj|image|picture|foto|photo|draw|desine)\b',
                    r'\b(kreye|create|make|generate)\b.*\b(imaj|image)\b',
                ],
                'responses': [
                    "Pou kreye yon imaj, itilize seksyon 'Kreye Imaj' epi:\n1. Dekri imaj ou vle wè (an Kreyòl oswa Franse)\n2. Klike 'Jenere Imaj'\n3. Tann kèk segond\n\nKi kalite imaj ou ta renmen kreye?",
                ]
            },
            
            # Video generation
            'video': {
                'patterns': [
                    r'\b(videyo|video|animation)\b',
                ],
                'responses': [
                    "Pou kreye videyo:\n1. Ale nan seksyon 'Kreye Video'\n2. Dekri videyo ou vle\n3. Chwazi estil: wave, circles, stars, oswa gradient\n\nKi estil animasyon ou prefere?",
                ]
            },
            
            # Problem/error
            'problem': {
                'patterns': [
                    r'\b(pwoblèm|problem|error|erè|pa mache|not work)\b',
                ],
                'responses': [
                    "Mwen regrete ou gen pwoblèm. Pou m ka ede w pi byen:\n1. Eksplike ki pwoblèm ou genyen\n2. Di m ki mesaj erè ou wè (si gen)\n3. Eksplike sa ou t ap eseye fè\n\nBay m plis detay tanpri.",
                ]
            },
            
            # Yes/No
            'affirmation': {
                'patterns': [
                    r'^\s*(wi|yes|oui|ok|okay|d\'accord)\s*$',
                ],
                'responses': [
                    "Byen! Kontinye di m sa ou bezwen.",
                    "Pèfè! Kisa ou ta renmen fè apre sa?",
                ]
            },
            
            'negation': {
                'patterns': [
                    r'^\s*(non|no|pa)\s*$',
                ],
                'responses': [
                    "Okè, pa gen pwoblèm. Ki lòt bagay ou ta renmen eseye?",
                ]
            },
        }
    
    def generate(self, prompt, max_length=300, use_web_search=True):
        """Generate smart response based on pattern matching"""
        prompt = prompt.strip()
        prompt_lower = prompt.lower()
        
        # Store in context
        self.context.append(prompt_lower)
        if len(self.context) > 5:
            self.context.pop(0)
        
        # 0. PRIORITY: Check if web search is needed/beneficial
        if use_web_search:
            web_response = self._try_web_search(prompt)
            if web_response:
                return web_response
        
        # 1. Check user training examples
        if self.user_training:
            best_match = None
            best_similarity = 0
            
            for example in self.user_training:
                similarity = self._calculate_similarity(prompt_lower, example['user_message'])
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = example
            
            # If good match found (>70% similar), use it
            if best_similarity > 0.7:
                self._increment_usage(best_match['id'])
                return best_match['response']
        
        # 2. Fall back to pattern matching
        for category, data in self.patterns.items():
            for pattern in data['patterns']:
                if re.search(pattern, prompt_lower, re.IGNORECASE):
                    response = random.choice(data['responses'])
                    return self._personalize_response(response, prompt)
        
        # 3. If no pattern matched, use intelligent generic response
        return self._generate_generic_response(prompt)
    
    def _try_web_search(self, prompt):
        """Try to get answer from web search"""
        try:
            from models.web_search import get_web_searcher
            
            searcher = get_web_searcher()
            
            # Check if this prompt needs web search
            if searcher.should_search(prompt):
                result = searcher.search_and_summarize(prompt)
                if result:
                    return result
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Web search failed: {e}")
        
        return None
    
    def _calculate_similarity(self, text1, text2):
        """Calculate text similarity (Jaccard index)"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _increment_usage(self, conversation_id):
        """Increment usage count for a training example"""
        try:
            from database.training_models import TrainingConversation
            from database.models import db
            
            conv = TrainingConversation.query.get(conversation_id)
            if conv:
                conv.used_count += 1
                db.session.commit()
        except Exception:
            pass  # Silently fail if database unavailable
    
    def _personalize_response(self, response, prompt):
        """Add personalization to responses"""
        # Add user's topic if detected
        response = response.replace("{topic}", self._extract_topic(prompt))
        return response
    
    def _extract_topic(self, prompt):
        """Extract main topic from prompt"""
        # Remove common words
        words = prompt.lower().split()
        stop_words = {'a', 'an', 'ak', 'de', 'la', 'le', 'li', 'mwen', 'ou', 'pou', 'se', 'the', 'is', 'are'}
        content_words = [w for w in words if w not in stop_words and len(w) > 2]
        
        if content_words:
            return content_words[0]
        return "sa"
    
    def _generate_generic_response(self, prompt):
        """Generate intelligent generic response"""
        
        # Check if it's a question
        is_question = any(q in prompt.lower() for q in ['ki', 'kisa', 'kijan', 'what', 'how', 'why', 'who', 'when', 'where', 'comment', 'pourquoi'])
        
        if is_question:
            return self._generate_question_response(prompt)
        
        # Check if it's a statement or command
        if any(c in prompt.lower() for c in ['fè', 'kreye', 'make', 'create', 'generate', 'show']):
            return self._generate_action_response(prompt)
        
        # Generic conversational response
        responses = [
            f"Mwen tande w. Ou ap pale de '{self._extract_topic(prompt)}'. Ka ou bay m plis enfòmasyon pou m ka ede w pi byen?",
            f"Enteresan! Pou m reponn pi byen sou '{self._extract_topic(prompt)}', di m egzakteman kisa ou vle konnen.",
            "Mwen konprann. Kisa espesyalman ou ta renmen konnen? Bay m plis detay.",
            "Sa se yon bon kesyon. Pou m ede w kòrèkteman, eksplike m plis sa ou bezwen.",
        ]
        
        return random.choice(responses)
    
    def _generate_question_response(self, prompt):
        """Generate response for questions"""
        responses = [
            f"Eksèlan kesyon sou '{self._extract_topic(prompt)}'! Men sa mwen ka di w:\n\nPou reponn sa byen, mwen ta bezwen konnen:\n1. Kontèks la\n2. Objektif ou a\n3. Ki enfòmasyon espesifik ou chèche\n\nBay m plis detay tanpri.",
            
            f"Pou kesyon sa a sou '{self._extract_topic(prompt)}', mwen ka ede w si ou bay m plis enfòmasyon. Ki aspè espesifik ou enterese?",
            
            "Mwen wè ou gen yon kesyon enpòtan. Pou m bay ou yon bon repons:\n- Eksplike kontèks la\n- Di m sa ou te eseye deja\n- Espesifye sa ou bezwen konnen\n\nKisa pami sa yo ou ka pataje?",
        ]
        
        return random.choice(responses)
    
    def _generate_action_response(self, prompt):
        """Generate response for action requests"""
        topic = self._extract_topic(prompt)
        
        responses = [
            f"Pou fè '{topic}', mwen ka gide w! Men etap yo:\n\n1. Dekri egzakteman sa ou vle\n2. Bay m tout detay enpòtan\n3. Mwen pral kreye sa pou ou\n\nKòmanse ak deskripsyon detaye ou a.",
            
            f"Mwen ka ede w kreye sa! Pou '{topic}', mwen bezwen:\n- Yon deskripsyon klè\n- Preferans ou yo\n- Objektif final la\n\nBay m plis enfòmasyon.",
        ]
        
        return random.choice(responses)

# Singleton instance
_smart_fallback = None

def get_smart_fallback():
    """Get singleton instance of smart fallback"""
    global _smart_fallback
    if _smart_fallback is None:
        _smart_fallback = SmartFallback()
    return _smart_fallback

