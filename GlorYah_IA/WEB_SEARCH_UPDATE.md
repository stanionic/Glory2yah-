# Web Search Integration - Code to Add

## Update chat route in app.py

Replace the existing `/chat` route with this enhanced version:

```python
@app.route('/chat', methods=['POST'])
def chat():
    """Génération de texte via AI avec recherche web"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Ou dwe ekri yon mesaj'}), 400
        
        prompt = data.get('prompt', '').strip()
        mode = data.get('mode', 'chat')
        use_web_search = data.get('web_search', False)  # NEW: Web search option
        
        if not prompt:
            return jsonify({'error': 'Ou dwe ekri yon mesaj'}), 400
        
        if len(prompt) > 5000:
            return jsonify({'error': 'Mesaj la two long (maksimòm 5000 karaktè)'}), 400
        
        # Génération de la réponse
        try:
            if mode == 'code':
                response = generators.code_gen.generate(prompt)
            else:
                # Pass web_search flag to generator
                response = generators.text_gen.generate(prompt, use_web_search=use_web_search)
        except Exception as gen_error:
            logger.error(f"Generation error: {gen_error}")
            response = "Mwen regrete, mwen gen yon pwoblèm. Tanpri eseye ankò."
        
        # Sauvegarde dans l'historique
        try:
            chat_entry = ChatHistory(
                prompt=prompt,
                response=response,
                mode=mode,
                timestamp=datetime.now()
            )
            db.session.add(chat_entry)
            db.session.commit()
        except Exception as db_error:
            logger.error(f"Database error: {db_error}")
            db.session.rollback()
        
        return jsonify({
            'success': True,
            'response': response,
            'timestamp': datetime.now().strftime('%H:%M'),
            'web_search_used': use_web_search  # NEW: Indicate if web search was used
        })
        
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return jsonify({'error': f'Erè: {str(e)}'}), 500
```

## Update TextGenerator

In `models/text_generator.py`, update the generate method:

```python
def generate(self, prompt, max_length=300, temperature=0.7, use_web_search=False):
    """Génération de texte avec option de recherche web"""
    if not self.generator:
        # Use smart fallback with web search option
        return self._fallback_response(prompt, use_web_search)
    
    try:
        # ... existing code ...
    except Exception as e:
        logger.error(f"Generation error: {e}")
        return self._fallback_response(prompt, use_web_search)

def _fallback_response(self, prompt, use_web_search=False):
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
```

## Add to requirements-basic.txt

Add web search dependencies:

```
# Web Search
requests==2.31.0
beautifulsoup4==4.12.2
lxml==4.9.3
```

## Update Frontend (main.js)

Add web search toggle in the chat interface:

```javascript
// Add to sendMessage function
function sendMessage() {
    const message = document.getElementById('userInput').value.trim();
    const useWebSearch = document.getElementById('webSearchToggle').checked;
    
    if (!message) return;
    
    // ... existing code ...
    
    fetch('/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            prompt: message,
            mode: 'chat',
            web_search: useWebSearch  // Include web search flag
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            addMessage(data.response, 'assistant');
            
            // Show indicator if web search was used
            if (data.web_search_used) {
                showWebSearchIndicator();
            }
        }
    });
}

function showWebSearchIndicator() {
    // Add visual indicator that web search was used
    const indicator = document.createElement('div');
    indicator.className = 'web-search-indicator';
    indicator.innerHTML = '🌐 Rechèch entènèt itilize';
    document.querySelector('.chat-messages').appendChild(indicator);
    
    setTimeout(() => indicator.remove(), 3000);
}
```

## Update HTML (index.html)

Add web search toggle in the chat interface:

```html
<div class="chat-controls">
    <input type="text" id="userInput" placeholder="Ekri mesaj ou...">
    <label class="web-search-toggle">
        <input type="checkbox" id="webSearchToggle">
        <span>🌐 Rechèch entènèt</span>
    </label>
    <button onclick="sendMessage()">Voye</button>
</div>

<style>
.web-search-toggle {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 5px 10px;
    background: #ecf0f1;
    border-radius: 5px;
    cursor: pointer;
}

.web-search-toggle:hover {
    background: #d5dbdb;
}

.web-search-indicator {
    background: #3498db;
    color: white;
    padding: 8px 15px;
    border-radius: 5px;
    margin: 10px 0;
    text-align: center;
    animation: fadeIn 0.3s;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(-10px); }
    to { opacity: 1; transform: translateY(0); }
}
</style>
```

## Example Usage

After implementation:

```javascript
// User asks: "Ki sa ki pase ann Ayiti jodi a?"
// With web search enabled:
// Response: "Voici sa mwen jwenn sou entènèt:
//
// 1. Haiti News Today
//    Latest developments in Haiti...
//    🔗 https://example.com/haiti-news
//
// 2. Current Events
//    Recent updates about...
//    🔗 https://example.com/updates
```

This integrates web search seamlessly into the chat!
