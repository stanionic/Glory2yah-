"""
Générateur de code
Version améliorée avec détection de langage et templates
"""

import re
from .text_generator import TextGenerator
import logging

logger = logging.getLogger(__name__)

class CodeGenerator(TextGenerator):
    def __init__(self):
        """Initialisation du générateur de code"""
        super().__init__()
        
        self.code_templates = {
            'python': {
                'function': '''def {name}({params}):
    """
    {description}
    """
    # Votre code ici
    pass
''',
                'class': '''class {name}:
    """
    {description}
    """
    def __init__(self):
        pass
''',
            },
            'javascript': {
                'function': '''function {name}({params}) {{
    // {description}
    // Votre code ici
}}
''',
                'class': '''class {name} {{
    constructor() {{
        // {description}
    }}
}}
''',
            },
            'html': {
                'page': '''<!DOCTYPE html>
<html lang="ht">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
</head>
<body>
    <h1>{title}</h1>
    <!-- Votre contenu ici -->
</body>
</html>
''',
            },
        }
    

    def _is_code_request(self, prompt):
        """Check if the prompt is actually requesting code"""
        prompt_lower = prompt.lower()
        
        # Code keywords
        code_keywords = [
            'code', 'kòd', 'program', 'pwogram', 'script',
            'function', 'fonksyon', 'class', 'klas',
            'python', 'javascript', 'html', 'css', 'java', 'sql',
            'write', 'ekri', 'create', 'kreye', 'generate', 'jenere',
            'def ', 'const ', 'var ', 'let ', 'import', 'function(',
        ]
        
        # Check if any code keyword is present
        return any(keyword in prompt_lower for keyword in code_keywords)

    def generate(self, prompt):
        """Génération de code spécifique"""
        try:
            # Check if this is actually a code request
            if not self._is_code_request(prompt):
                # Not a code request, use smart fallback
                from .smart_fallback import get_smart_fallback
                fallback = get_smart_fallback()
                return fallback.generate(prompt)
            
            language = self._detect_language(prompt)
            logger.info(f"Detected language: {language}")
            
            code_type = self._detect_code_type(prompt)
            logger.info(f"Detected code type: {code_type}")
            
            template_code = self._try_template(prompt, language, code_type)
            if template_code:
                return template_code
            
            code_prompt = self._create_code_prompt(prompt, language)
            
            if not self.generator:
                return self._fallback_code(prompt, language, code_type)
            
            result = self.generator(
                code_prompt,
                max_length=600,
                temperature=0.3,
                top_p=0.95,
                do_sample=True
            )
            
            generated = result[0]['generated_text']
            code = self._extract_code(generated)
            
            if code and len(code.strip()) > 10:
                return code
            else:
                return self._fallback_code(prompt, language, code_type)
            
        except Exception as e:
            logger.error(f"Code generation error: {e}")
            return f"# Erè nan jenere kòd la: {str(e)}\n# Tanpri eseye ak yon demann pi senp."
    
    def _detect_language(self, prompt):
        """Détecte le langage de programmation demandé"""
        prompt_lower = prompt.lower()
        
        languages = {
            'python': ['python', 'py', 'def ', 'import', 'class ', 'django', 'flask'],
            'javascript': ['javascript', 'js', 'function', 'const ', 'let ', 'var ', 'react', 'node'],
            'html': ['html', 'web page', 'webpage', 'paj web', '<html>', 'site web'],
            'css': ['css', 'style', 'stil'],
            'java': ['java', 'class ', 'public static'],
            'c++': ['c++', 'cpp', 'cout', 'iostream'],
            'sql': ['sql', 'select', 'database', 'baz done'],
        }
        
        for lang, keywords in languages.items():
            if any(keyword in prompt_lower for keyword in keywords):
                return lang
        
        return 'python'
    
    def _detect_code_type(self, prompt):
        """Détecte le type de code demandé"""
        prompt_lower = prompt.lower()
        
        if any(word in prompt_lower for word in ['function', 'fonksyon', 'def ', 'metòd']):
            return 'function'
        elif any(word in prompt_lower for word in ['class', 'klas', 'object', 'objè']):
            return 'class'
        elif any(word in prompt_lower for word in ['page', 'paj', 'html', 'website']):
            return 'page'
        elif any(word in prompt_lower for word in ['script', 'program', 'pwogram']):
            return 'script'
        else:
            return 'snippet'
    
    def _try_template(self, prompt, language, code_type):
        """Essaie d'utiliser un template de code"""
        if language not in self.code_templates:
            return None
        
        if code_type not in self.code_templates[language]:
            return None
        
        info = self._extract_info_from_prompt(prompt)
        
        try:
            template = self.code_templates[language][code_type]
            code = template.format(**info)
            return code
        except KeyError:
            return None
    
    def _extract_info_from_prompt(self, prompt):
        """Extrait les informations du prompt"""
        info = {
            'name': 'myFunction',
            'params': '',
            'description': prompt[:100],
            'title': 'My Page'
        }
        
        name_match = re.search(r'(?:appel[eé]|name|non|ki rele)\s+["\']?(\w+)["\']?', prompt, re.IGNORECASE)
        if name_match:
            info['name'] = name_match.group(1)
        
        params_match = re.search(r'(?:avec|with|ak)\s+(?:paramètres?|parameters?|paramèt)\s*:?\s*(.+?)(?:\.|$)', prompt, re.IGNORECASE)
        if params_match:
            info['params'] = params_match.group(1).strip()
        
        return info
    
    def _create_code_prompt(self, prompt, language):
        """Crée un prompt optimisé pour la génération de code"""
        code_prompt = f"""# Kreyòl Request: {prompt}

# Generate {language} code
# The code should be functional and well-commented

```{language}
"""
        return code_prompt
    
    def _extract_code(self, generated_text):
        """Extraction du code du texte généré"""
        try:
            code_match = re.search(r'```(?:\w+)?\n(.*?)```', generated_text, re.DOTALL)
            if code_match:
                return code_match.group(1).strip()
            
            code_match = re.search(r'Code:\s*(.*?)(?:\n\n|\Z)', generated_text, re.DOTALL)
            if code_match:
                return code_match.group(1).strip()
            
            lines = generated_text.split('\n')
            code_lines = []
            in_code = False
            
            for line in lines:
                if line.strip().startswith('#') and not in_code:
                    in_code = True
                    code_lines.append(line)
                elif in_code:
                    code_lines.append(line)
            
            if code_lines:
                return '\n'.join(code_lines)
            
            return generated_text
            
        except Exception as e:
            logger.error(f"Code extraction error: {e}")
            return generated_text
    
    def _fallback_code(self, prompt, language, code_type):
        """Code de secours quand la génération échoue"""
        fallback_codes = {
            'python': {
                'function': f'''# Fonction demandée: {prompt[:50]}
def ma_fonction():
    """
    TODO: Implémenter la logique pour: {prompt[:50]}
    """
    print("Fonksyon an ap travay!")
    # Ajoute kòd ou isit la
    pass

# Exemple d'utilisation
if __name__ == "__main__":
    ma_fonction()
''',
                'class': f'''# Classe demandée: {prompt[:50]}
class MaClasse:
    """
    TODO: Implémenter la logique pour: {prompt[:50]}
    """
    def __init__(self):
        self.nom = "MANDEMMAPBAW"
    
    def methode(self):
        print(f"Bonjou de {{self.nom}}!")

# Exemple d'utilisation
if __name__ == "__main__":
    obj = MaClasse()
    obj.methode()
''',
            },
            'javascript': {
                'function': f'''// Fonction demandée: {prompt[:50]}
function maFonction() {{
    // TODO: Implémenter la logique pour: {prompt[:50]}
    console.log("Fonksyon an ap travay!");
    // Ajoute kòd ou isit la
}}

// Exemple d'utilisation
maFonction();
''',
            },
            'html': {
                'page': f'''<!DOCTYPE html>
<html lang="ht">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MANDEMMAPBAW - {prompt[:30]}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
        }}
        h1 {{
            color: #3498db;
        }}
    </style>
</head>
<body>
    <h1>MANDEMMAPBAW</h1>
    <p>{prompt}</p>
    <!-- TODO: Ajoute kontni paj ou a isit la -->
</body>
</html>
''',
            }
        }
        
        try:
            return fallback_codes.get(language, {}).get(
                code_type,
                f"# Code pour: {prompt}\n# TODO: Implémenter"
            )
        except Exception:
            return f"# Code pour: {prompt}\n# TODO: Implémenter"
