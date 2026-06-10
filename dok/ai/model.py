#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modèle d'IA médicale local pour Dòk GlorYah
Système basé sur des règles intelligentes
"""

import re
from typing import Dict

class DokGlorYahAI:
    """
    IA médicale locale utilisant un système de règles
    pour classifier et répondre aux symptômes en créole haïtien
    """
    
    def __init__(self):
        """Initialiser les patterns de symptômes"""
        
        # Symptômes URGENTS (🔴)
        self.urgent_patterns = [
            # Cardiovasculaire
            r'\b(doulè|doule|fè mal|mal).{0,20}(kè|pwatrin|lestomak)\b',
            r'\b(kè w|kè m).{0,15}(bat|rape|fè mal)\b',
            r'\bpa ka respire\b',
            r'\bsouf kout\b',
            r'\bsouflè\b',
            
            # Neurologique
            r'\btèt.{0,15}(fè mal|tounen|vire)\b.*\b(anpil|grav|pa sipòte)\b',
            r'\b(pa wè|pèdi vizyon|avèg|je fèmen)\b',
            r'\bkonvulsion\b',
            r'\bpa ka pale\b',
            r'\bpèdi konesans\b',
            r'\bevanoui\b',
            r'\bparalizi\b',
            
            # Hémorragie
            r'\b(san|kaka san|pipi san|vomi san)\b',
            r'\bsenyen\b',
            r'\bemworaji\b',
            
            # Trauma
            r'\b(aksidan|blese|kase zo|frakti)\b',
            r'\bchoke\b',
            r'\bbrile\b',
            
            # Grossesse
            r'\b(ansent|gwosès).{0,20}(doule|senyen|pwoblèm)\b',
            r'\bbebe.{0,15}(pa bouje|sispann)\b',
            
            # Fièvre sévère
            r'\b(lafyèv|cho anpil).{0,20}(anpil|pa desann|40|41)\b',
            
            # Déshydratation sévère
            r'\b(dyare|vomi).{0,30}(anpil|pa sispann|tout tan)\b',
            r'\bpa ka bwè\b',
            
            # Douleur intense
            r'\bdoulè.{0,15}(teren|pa sipòte|anpil)\b',
            r'\bfè mal.{0,15}(anpil|twòp|pa sipòte)\b',
        ]
        
        # Symptômes MOYENS (🟡)
        self.moderate_patterns = [
            r'\b(lafyèv|cho|frison)\b',
            r'\b(toux|tous|gripi|grip)\b',
            r'\b(doule vant|vant fè mal|lestomak fè mal)\b',
            r'\b(dyare|grangou|pa gen apeti)\b',
            r'\b(fatig|feb|pa gen fòs)\b',
            r'\b(mal tèt|migrain)\b',
            r'\b(vomi|anvi vomi|anvi rann)\b',
            r'\b(etoudi|pa ka konkantre)\b',
            r'\b(mal gòj|gòj fè mal)\b',
            r'\b(bouton|gratel|po)\b',
        ]
        
    def analyze(self, text: str) -> Dict:
        """
        Analyser le texte et retourner une réponse structurée
        
        Args:
            text: Description des symptômes en créole ou français
            
        Returns:
            Dict avec icon, level, response et warning
        """
        text_lower = text.lower()
        
        # Déterminer le niveau de gravité
        level, icon = self._classify_severity(text_lower)
        
        # Générer la réponse
        response_text = self._generate_response(text_lower, level)
        
        # Avertissement standard
        warning = "⚠️ Sa pa ranplase konsiltasyon ak yon doktè."
        
        return {
            'icon': icon,
            'level': level,
            'response': response_text,
            'warning': warning
        }
    
    def _classify_severity(self, text: str):
        """
        Classifier la gravité des symptômes
        
        Returns:
            Tuple (niveau, icône)
        """
        # Vérifier urgence
        for pattern in self.urgent_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return ('WOUJ', '🔴')
        
        # Vérifier modéré
        for pattern in self.moderate_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return ('JÒN', '🟡')
        
        # Par défaut: léger
        return ('VÈT', '🟢')
    
    def _generate_response(self, text: str, level: str) -> str:
        """
        Générer une réponse appropriée selon le niveau
        """
        if level == 'WOUJ':
            return self._urgent_response(text)
        elif level == 'JÒN':
            return self._moderate_response(text)
        else:
            return self._mild_response(text)
    
    def _urgent_response(self, text: str) -> str:
        """Réponse pour cas urgent"""
        responses = []
        
        # Cardiovasculaire
        if re.search(r'\b(kè|pwatrin|souf|respire)\b', text):
            responses.append("Sentòm ou yo ka endike yon pwoblèm kè oswa respiratwa.")
        
        # Neurologique
        if re.search(r'\b(tèt|konvulsion|pa ka pale|pèdi konesans)\b', text):
            responses.append("Sa ka yon pwoblèm serebral seryè.")
        
        # Hémorragie
        if re.search(r'\b(san|senyen|emworaji)\b', text):
            responses.append("Pèt san ka danjere anpil.")
        
        # Trauma
        if re.search(r'\b(aksidan|blese|kase)\b', text):
            responses.append("Blesi ou a bezwen atansyon medikal imedya.")
        
        # Grossesse
        if re.search(r'\b(ansent|gwosès|bebe)\b', text):
            responses.append("Pandan gwosès, siy sa yo bezwen konsiltasyon ijans.")
        
        base = " ".join(responses) if responses else "Sa sanble grav."
        
        return f"""{base}

**Sentòm ou yo ka danjere.**

🚨 **Ki sa pou w fè kounye a:**
• Ale lopital pi vit posib
• Si ou pa ka deplase, rele anbyilans oswa jwenn èd
• Pa tann plis tan
• Kontakte yon pwofesyonèl sou WhatsApp si ou bezwen sipò

Tanpri, pa neglije sentòm sa yo."""
    
    def _moderate_response(self, text: str) -> str:
        """Réponse pour cas modéré"""
        advice = []
        
        # Fièvre
        if re.search(r'\b(lafyèv|cho|frison)\b', text):
            advice.append("• Pran anpil dlo pou evite dezidwatasyon")
            advice.append("• Repoze kò w")
            advice.append("• Aplike konprès frèt si lafyèv la wo anpil")
        
        # Douleur
        if re.search(r'\b(doule|fè mal|mal)\b', text):
            advice.append("• Repoze zòn ki fè mal la")
            advice.append("• Evite aktivite ki ka agrave doulè a")
        
        # Digestif
        if re.search(r'\b(vant|dyare|vomi|lestomak)\b', text):
            advice.append("• Bwè dlo regilyèman")
            advice.append("• Manje manje lejè")
            advice.append("• Evite manje ki pikant oswa gra")
        
        # Respiratoire
        if re.search(r'\b(toux|tous|gripi|grip)\b', text):
            advice.append("• Repoze vwa ou")
            advice.append("• Bwè likid cho (te, soup)")
            advice.append("• Rete nan yon kote ki gen bon vantilasyon")
        
        # Fatigue
        if re.search(r'\b(fatig|feb|pa gen fòs)\b', text):
            advice.append("• Dòmi ase (7-8 èdtan)")
            advice.append("• Manje aliman nitritif")
        
        advice_text = "\n".join(advice) if advice else "• Swiv sentòm yo ak atansyon"
        
        return f"""Sentòm ou yo merite atansyon, men yo pa sanble ijans pou kounye a.

**Konsèy:**
{advice_text}

**Lè pou w wè doktè:**
• Si sentòm yo pa amelyore nan 2-3 jou
• Si yo vin pi mal
• Si ou devlope lòt sentòm

Si w enkyete, pa ezite kontakte yon pwofesyonèl sante."""
    
    def _mild_response(self, text: str) -> str:
        """Réponse pour cas léger"""
        return """Sentòm ou yo sanble lejè pou kounye a.

**Rekòmandasyon jeneral:**
• Pran anpil repo
• Bwè anpil dlo
• Manje aliman san ekilib
• Swiv izyèn debaz (lave men, pwòpte)

**Lè pou w enkyete:**
• Si sentòm yo vin pi grav
• Si ou devlope lafyèv oswa doule enten
• Si sa dire plis pase yon semèn

Kontinye siveyans sentòm ou yo. Si gen dout, kontakte yon pwofesyonèl sante."""

# Test du module si exécuté directement
if __name__ == '__main__':
    ai = DokGlorYahAI()
    
    # Tests
    tests = [
        "Mwen gen mal nan kè mwen",
        "Mwen gen yon ti toux",
        "Tèt mwen ap vire epi m pa wè byen",
    ]
    
    print("Test modèl IA medikal:\n")
    for test in tests:
        result = ai.analyze(test)
        print(f"Sentòm: {test}")
        print(f"Nivo: {result['icon']} {result['level']}")
        print(f"Repons: {result['response'][:100]}...")
        print("-" * 50)
