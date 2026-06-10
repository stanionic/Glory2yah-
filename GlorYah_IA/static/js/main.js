// MANDEMMAPBAW - JavaScript Prensipal

let currentMode = 'chat';
let chatHistory = [];

// Fonksyon pou voye mesaj
async function sendMessage() {
    const input = document.getElementById('prompt-input');
    const prompt = input.value.trim();
    const useWebSearch = document.getElementById('webSearchToggle').checked;

    if (!prompt) {
        alert('Tanpri ekri yon mesaj!');
        return;
    }

    // Afiche mesaj itilizatè a
    addMessage(prompt, 'user');

    // Netwaye chan an
    input.value = '';

    // Afiche endikatè chajman
    showLoading(true);

    try {
        // Voye reqèt la
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                prompt: prompt,
                mode: currentMode,
                web_search: useWebSearch  // Include web search flag
            })
        });
        
        const data = await response.json();

        if (data.success) {
            // Afiche repons AI a
            addMessage(data.response, 'bot', data.timestamp);

            // Show indicator if web search was used
            if (data.web_search_used) {
                showWebSearchIndicator();
            }

            // Mete ajou istwa a
            loadHistory();
        } else {
            addMessage(`Erè: ${data.error}`, 'bot');
        }
        
    } catch (error) {
        addMessage(`Erè nan koneksyon an: ${error.message}`, 'bot');
    } finally {
        showLoading(false);
    }
}

// Fonksyon pou ajoute mesaj
function addMessage(text, sender, time = null) {
    const chatMessages = document.getElementById('chat-messages');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = `<strong>${sender === 'user' ? 'Ou:' : 'MANDEMMAPBAW:'}</strong> ${text}`;
    
    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-time';
    timeDiv.textContent = time || new Date().toLocaleTimeString('ht-HT', { 
        hour: '2-digit', 
        minute: '2-digit' 
    });
    
    messageDiv.appendChild(contentDiv);
    messageDiv.appendChild(timeDiv);
    chatMessages.appendChild(messageDiv);
    
    // Scroll anba
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Fonksyon pou montre/kache chajman
function showLoading(show) {
    const loadingDiv = document.getElementById('loading');
    loadingDiv.style.display = show ? 'flex' : 'none';
}

// Fonksyon pou jenere imaj
async function generateImage() {
    const prompt = document.getElementById('image-prompt').value.trim();
    
    if (!prompt) {
        alert('Tanpri dekri imaj ou vle a!');
        return;
    }
    
    showLoading(true);
    const imageResult = document.getElementById('image-result');
    imageResult.innerHTML = '<div class="spinner-border text-warning"></div>';
    
    try {
        const response = await fetch('/generate-image', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ prompt: prompt })
        });
        
        const data = await response.json();
        
        if (data.success) {
            imageResult.innerHTML = `
                <div class="generated-media-container">
                    <img src="${data.image_url}" alt="Imaj jenere" class="generated-media img-fluid">
                    <div class="mt-2">
                        <button class="btn btn-sm btn-success" onclick="downloadFile('image', '${data.filename}')">
                            <i class="fas fa-download"></i> Telechaje Imaj
                        </button>
                    </div>
                </div>
            `;
            
            // Ajoute nan chat tou
            addMessage(`Mwen fin kreye imaj pou: "${prompt}"`, 'bot');
        } else {
            imageResult.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
        }
        
    } catch (error) {
        imageResult.innerHTML = `<div class="alert alert-danger">Erè: ${error.message}</div>`;
    } finally {
        showLoading(false);
    }
}

// Fonksyon pou jenere videyo
async function generateVideo() {
    const prompt = document.getElementById('video-prompt').value.trim();
    
    if (!prompt) {
        alert('Tanpri dekri videyo ou vle a!');
        return;
    }
    
    showLoading(true);
    const videoResult = document.getElementById('video-result');
    videoResult.innerHTML = '<div class="spinner-border text-danger"></div>';
    
    try {
        const response = await fetch('/generate-video', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ prompt: prompt })
        });
        
        const data = await response.json();
        
        if (data.success) {
            videoResult.innerHTML = `
                <div class="generated-media-container">
                    <video src="${data.video_url}" controls class="generated-media img-fluid"></video>
                    <div class="mt-2">
                        <button class="btn btn-sm btn-success" onclick="downloadFile('video', '${data.filename}')">
                            <i class="fas fa-download"></i> Telechaje Video
                        </button>
                    </div>
                </div>
            `;
            
            addMessage(`Mwen fin kreye videyo pou: "${prompt}"`, 'bot');
        } else {
            videoResult.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
        }
        
    } catch (error) {
        videoResult.innerHTML = `<div class="alert alert-danger">Erè: ${error.message}</div>`;
    } finally {
        showLoading(false);
    }
}

// Fonksyon pou jenere kòd
async function generateCode() {
    const prompt = document.getElementById('code-prompt').value.trim();
    
    if (!prompt) {
        alert('Tanpri dekri kòd ou vle a!');
        return;
    }
    
    showLoading(true);
    const codeResult = document.getElementById('code-result');
    codeResult.innerHTML = '<div class="spinner-border text-success"></div>';
    
    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                prompt: prompt,
                mode: 'code'
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            codeResult.innerHTML = `
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-code"></i> Kòd Jenere
                    </div>
                    <div class="card-body p-0">
                        <pre class="m-0"><code>${escapeHtml(data.response)}</code></pre>
                    </div>
                </div>
            `;
            
            // Ajoute nan chat
            addMessage(`Mwen fin jenere kòd pou: "${prompt}"`, 'bot');
        } else {
            codeResult.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
        }
        
    } catch (error) {
        codeResult.innerHTML = `<div class="alert alert-danger">Erè: ${error.message}</div>`;
    } finally {
        showLoading(false);
    }
}

// Fonksyon pou telechaje fichye
function downloadFile(type, filename) {
    window.open(`/download/${type}/${filename}`, '_blank');
}

// Fonksyon pou chaje istwa
async function loadHistory() {
    try {
        const response = await fetch(`/history?mode=${currentMode}`);
        const data = await response.json();
        
        if (data.success) {
            const historyList = document.getElementById('history-list');
            historyList.innerHTML = '';
            
            data.history.slice(0, 10).forEach(item => {
                const historyItem = document.createElement('div');
                historyItem.className = 'history-item';
                historyItem.innerHTML = `
                    <div class="fw-bold">${item.prompt.substring(0, 50)}...</div>
                    <div class="time">${item.timestamp}</div>
                `;
                historyItem.onclick = () => {
                    document.getElementById('prompt-input').value = item.prompt;
                };
                historyList.appendChild(historyItem);
            });
        }
    } catch (error) {
        console.error('Erè chajman istwa:', error);
    }
}

// Fonksyon pou efase istwa
async function clearHistory() {
    if (!confirm('Èske ou sèten ou vle efase tout istwa a?')) return;
    
    try {
        const response = await fetch('/admin/delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ mode: currentMode })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('Istwa efase avèk siksè!');
            loadHistory();
            
            // Netwaye chat
            document.getElementById('chat-messages').innerHTML = `
                <div class="message bot">
                    <div class="message-content">
                        <strong>MANDEMMAPBAW:</strong> Istwa konvèsasyon an efase. Komanse nouvo konvèsasyon!
                    </div>
                    <div class="message-time">Jodi a</div>
                </div>
            `;
        }
    } catch (error) {
        alert(`Erè: ${error.message}`);
    }
}

// Fonksyon pou escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Fonksyon pou montre endikatè rechèch entènèt
function showWebSearchIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'web-search-indicator';
    indicator.innerHTML = '🌐 Rechèch entènèt itilize';
    document.getElementById('chat-messages').appendChild(indicator);

    setTimeout(() => indicator.remove(), 3000);
}

// Fonksyon pou handle enter key
function handleKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

// Chaje istwa lè paj la chaje
document.addEventListener('DOMContentLoaded', function() {
    loadHistory();
    
    // Setup mode selection
    document.querySelectorAll('[data-mode]').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            currentMode = this.getAttribute('data-mode');
            
            // Update UI
            document.querySelectorAll('[data-mode]').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            // Update placeholder
            const placeholders = {
                'chat': 'Ekri sa ou vle mande IA a...',
                'image': 'Dekri imaj ou vle kreye a...',
                'video': 'Dekri videyo ou vle kreye a...',
                'code': 'Dekri kòd ou vle jenere a...'
            };
            document.getElementById('prompt-input').placeholder = 
                placeholders[currentMode] + ' (Ou mèt ekri an Kreyòl oswa Fransè)';
            
            // Mete ajou istwa
            loadHistory();
        });
    });
});