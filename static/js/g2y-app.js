/* ═══════════════════════════════════════════════════════════
   GLORY2YAHPUB - JAVASCRIPT ENGINE
   Stories, Interactions, PWA Features
   ═══════════════════════════════════════════════════════════ */

// ═══ STORY VIEWER ═══
let currentStoryIndex = 0;
let storyTimer = null;

function openStory(index) {
    if (!STORIES_DATA || STORIES_DATA.length === 0) return;
    
    currentStoryIndex = index;
    const modal = document.getElementById('storyModal');
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    
    showStory(currentStoryIndex);
}

function closeStory() {
    const modal = document.getElementById('storyModal');
    modal.style.display = 'none';
    document.body.style.overflow = '';
    
    if (storyTimer) {
        clearTimeout(storyTimer);
        storyTimer = null;
    }
}

function showStory(index) {
    if (!STORIES_DATA || index < 0 || index >= STORIES_DATA.length) {
        closeStory();
        return;
    }
    
    const story = STORIES_DATA[index];
    const content = document.getElementById('storyContent');
    const info = document.getElementById('storyInfo');
    const progress = document.getElementById('storyProgress');
    
    // Build content
    if (story.video) {
        content.innerHTML = `<video src="${story.video}" autoplay muted playsinline style="width:100%;height:100%;object-fit:contain"></video>`;
    } else if (story.img) {
        content.innerHTML = `<img src="${story.img}" style="width:100%;height:100%;object-fit:contain" alt="${story.title}">`;
    } else {
        content.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:64px">📦</div>`;
    }
    
    // Build info
    info.innerHTML = `
        <div style="padding:20px;background:rgba(0,0,0,0.6);color:white;border-radius:12px">
            <h3 style="font-size:20px;margin-bottom:8px">${story.title}</h3>
            <p style="font-size:14px;margin-bottom:12px">${story.desc}</p>
            ${story.price > 0 ? `<div style="font-size:18px;font-weight:700;color:#FFD700">🪙 ${story.price} Gkach</div>` : ''}
            <a href="/ad/${story.id}" style="display:inline-block;margin-top:12px;padding:10px 20px;background:white;color:#002366;border-radius:20px;text-decoration:none;font-weight:600">Wè Detay</a>
        </div>
    `;
    
    // Progress bar
    progress.innerHTML = '';
    for (let i = 0; i < STORIES_DATA.length; i++) {
        const bar = document.createElement('div');
        bar.style.cssText = 'flex:1;height:3px;background:rgba(255,255,255,0.3);border-radius:2px;overflow:hidden';
        if (i < index) {
            bar.innerHTML = '<div style="width:100%;height:100%;background:white"></div>';
        } else if (i === index) {
            bar.innerHTML = '<div style="width:0;height:100%;background:white;animation:storyProgress 5s linear forwards"></div>';
        }
        progress.appendChild(bar);
    }
    
    // Auto-advance after 5s
    if (storyTimer) clearTimeout(storyTimer);
    storyTimer = setTimeout(() => nextStory(), 5000);
}

function nextStory() {
    if (currentStoryIndex < STORIES_DATA.length - 1) {
        currentStoryIndex++;
        showStory(currentStoryIndex);
    } else {
        closeStory();
    }
}

function prevStory() {
    if (currentStoryIndex > 0) {
        currentStoryIndex--;
        showStory(currentStoryIndex);
    }
}

// Add CSS for story progress animation
const style = document.createElement('style');
style.textContent = `
@keyframes storyProgress {
    from { width: 0; }
    to { width: 100%; }
}

.g2y-story-modal {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10000;
    display: none;
    align-items: center;
    justify-content: center;
}

.g2y-story-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0,0,0,0.9);
}

.g2y-story-viewer {
    position: relative;
    width: 100%;
    max-width: 500px;
    height: 90vh;
    background: #000;
    border-radius: 12px;
    overflow: hidden;
    z-index: 1;
}

.g2y-story-progress {
    position: absolute;
    top: 12px;
    left: 12px;
    right: 12px;
    display: flex;
    gap: 4px;
    z-index: 2;
}

.g2y-story-close {
    position: absolute;
    top: 12px;
    right: 12px;
    width: 36px;
    height: 36px;
    background: rgba(0,0,0,0.6);
    color: white;
    border: none;
    border-radius: 50%;
    font-size: 20px;
    cursor: pointer;
    z-index: 2;
}

.g2y-story-content {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
}

.g2y-story-info {
    position: absolute;
    bottom: 20px;
    left: 20px;
    right: 20px;
    z-index: 2;
}

.g2y-story-prev, .g2y-story-next {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 48px;
    height: 48px;
    background: rgba(0,0,0,0.5);
    color: white;
    border: none;
    border-radius: 50%;
    font-size: 28px;
    cursor: pointer;
    z-index: 2;
}

.g2y-story-prev { left: 12px; }
.g2y-story-next { right: 12px; }

@media (max-width: 768px) {
    .g2y-story-viewer {
        max-width: 100%;
        height: 100vh;
        border-radius: 0;
    }
}
`;
document.head.appendChild(style);

// Stories now rectangular grid - no horizontal scroll needed

// ═══ PWA INSTALL PROMPT ═══
let deferredPrompt;

window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    
    // Show install button if needed
    const installBtn = document.getElementById('installBtn');
    if (installBtn) {
        installBtn.style.display = 'block';
        installBtn.addEventListener('click', async () => {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                const { outcome } = await deferredPrompt.userChoice;
                deferredPrompt = null;
                installBtn.style.display = 'none';
            }
        });
    }
});

// ═══ NETWORK STATUS ═══
window.addEventListener('online', () => {
    showToast('✅ Koneksyon retabli');
});

window.addEventListener('offline', () => {
    showToast('⚠️ Pa gen koneksyon');
});

// ═══ PULL TO REFRESH (Mobile) ═══
let touchStartY = 0;
let touchEndY = 0;

document.addEventListener('touchstart', (e) => {
    touchStartY = e.touches[0].clientY;
}, { passive: true });

document.addEventListener('touchmove', (e) => {
    touchEndY = e.touches[0].clientY;
}, { passive: true });

document.addEventListener('touchend', () => {
    if (window.scrollY === 0 && touchEndY > touchStartY + 100) {
        location.reload();
    }
}, { passive: true });

// ═══ LAZY LOAD IMAGES ═══
if ('IntersectionObserver' in window) {
    const imageObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                if (img.dataset.src) {
                    img.src = img.dataset.src;
                    img.removeAttribute('data-src');
                }
                imageObserver.unobserve(img);
            }
        });
    });
    
    document.querySelectorAll('img[data-src]').forEach(img => {
        imageObserver.observe(img);
    });
}

// ═══ HAPTIC FEEDBACK (Mobile) ═══
function vibrate(duration = 10) {
    if ('vibrate' in navigator) {
        navigator.vibrate(duration);
    }
}

// Add vibration to buttons
document.addEventListener('click', (e) => {
    if (e.target.matches('button, .g2y-action-btn, .g2y-nav-item')) {
        vibrate(10);
    }
});

console.log('🎉 Glory2YahPub App Loaded');
