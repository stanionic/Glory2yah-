/**
 * Glory2YahPub - PWA Install Prompt System
 * Professional mobile installation experience
 * Handles Android (beforeinstallprompt), iOS (Safari), and standalone detection
 */

(function() {
    'use strict';

    // ===== CONFIGURATION =====
    const CONFIG = {
        STORAGE_KEY: 'gloryyah_install_prompt',
        POPUP_DELAY: 5000,         // 5 seconds before showing prompt
        POPUP_DELAY_INTERACTION: 3000, // 3 seconds after first interaction
        IOS_GUIDE_DELAY: 3000,     // 3 seconds before iOS guide
        ANALYTICS_ENDPOINT: '/api/pwa/analytics',
        SETTINGS_ENDPOINT: '/api/pwa/settings'
    };

    // ===== STATE =====
    let deferredPrompt = null;
    let isInstalled = false;
    let settings = null;
    let analyticsData = {
        device_type: '',
        browser: '',
        os: '',
        language: navigator.language || 'ht',
        install_prompt_displayed: false,
        install_completed: false,
        dismissed: false,
        user_id: null
    };

    // ===== UTILITY FUNCTIONS =====

    /**
     * Detect device and browser information
     */
    function getDeviceInfo() {
        const ua = navigator.userAgent;
        const info = {
            device_type: 'desktop',
            browser: 'unknown',
            os: 'unknown'
        };

        // Device type
        if (/Mobi|Android|iPhone|iPad|iPod/i.test(ua)) {
            info.device_type = 'mobile';
        } else if (/Tablet|iPad/i.test(ua)) {
            info.device_type = 'tablet';
        }

        // OS
        if (/Windows/i.test(ua)) info.os = 'windows';
        else if (/Mac OS/i.test(ua)) info.os = 'macos';
        else if (/Android/i.test(ua)) info.os = 'android';
        else if (/iPhone|iPad|iPod/i.test(ua)) info.os = 'ios';
        else if (/Linux/i.test(ua)) info.os = 'linux';

        // Browser
        if (/Chrome/i.test(ua) && !/Edge|Edg/i.test(ua)) info.browser = 'chrome';
        else if (/Safari/i.test(ua) && !/Chrome/i.test(ua)) info.browser = 'safari';
        else if (/Firefox/i.test(ua)) info.browser = 'firefox';
        else if (/Edg|Edge/i.test(ua)) info.browser = 'edge';
        else if (/Samsung/i.test(ua)) info.browser = 'samsung';
        else if (/Opera|OPR/i.test(ua)) info.browser = 'opera';

        return info;
    }

    /**
     * Check if app is already installed (standalone mode)
     */
    function checkIfInstalled() {
        if (window.matchMedia('(display-mode: standalone)').matches ||
            window.navigator.standalone === true) {
            isInstalled = true;
            analyticsData.install_completed = true;
            return true;
        }
        return false;
    }

    /**
     * Check if running on iOS Safari
     */
    function isIOSSafari() {
        const info = getDeviceInfo();
        return info.os === 'ios' && info.browser === 'safari';
    }

    /**
     * Load PWA settings from server
     */
    async function loadSettings() {
        try {
            const response = await fetch(CONFIG.SETTINGS_ENDPOINT);
            if (response.ok) {
                settings = await response.json();
                return settings;
            }
        } catch (e) {
            console.warn('Could not load PWA settings:', e);
        }
        // Default settings if server unavailable
        settings = {
            pwa_enabled: true,
            popup_title: 'Installer Glory2YahPub',
            popup_description: 'Accédez rapidement aux boutiques, publications, annonces et services depuis votre téléphone.',
            popup_button_text: 'Installer maintenant',
            popup_delay_seconds: 5,
            ios_guide_enabled: true
        };
        return settings;
    }

    /**
     * Get stored prompt state from LocalStorage
     */
    function getStoredState() {
        try {
            const stored = localStorage.getItem(CONFIG.STORAGE_KEY);
            return stored ? JSON.parse(stored) : null;
        } catch (e) {
            return null;
        }
    }

    /**
     * Save prompt state to LocalStorage
     */
    function saveState(state) {
        try {
            localStorage.setItem(CONFIG.STORAGE_KEY, JSON.stringify(state));
        } catch (e) {
            console.warn('Could not save install state:', e);
        }
    }

    /**
     * Check if we should show the install prompt based on stored state
     */
    function shouldShowPrompt() {
        const state = getStoredState();
        
        // Never show if already installed
        if (isInstalled) return false;
        
        // First visit - always show
        if (!state) {
            saveState({
                first_visit: true,
                prompt_displayed: false,
                dismissed: false,
                install_completed: false,
                first_visit_time: Date.now(),
                times_prompted: 0
            });
            return true;
        }

        // Don't show if already installed
        if (state.install_completed) return false;
        
        // Don't show if user dismissed
        if (state.dismissed) {
            // But show again after 7 days if dismissed
            const dismissedTime = state.dismissed_time || 0;
            const sevenDays = 7 * 24 * 60 * 60 * 1000;
            if (Date.now() - dismissedTime > sevenDays) {
                state.dismissed = false;
                state.times_prompted = 0;
                saveState(state);
                return true;
            }
            return false;
        }

        // Don't show if already prompted too many times (max 3)
        if (state.times_prompted >= 3) return false;

        return true;
    }

    /**
     * Send analytics to server
     */
    async function sendAnalytics(data) {
        try {
            const response = await fetch(CONFIG.ANALYTICS_ENDPOINT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify(data)
            });
            return response.ok;
        } catch (e) {
            console.warn('Analytics send failed:', e);
            return false;
        }
    }

    /**
     * Get CSRF token from meta tag
     */
    function getCSRFToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    // ===== INSTALL PROMPT UI =====

    /**
     * Create and show the install popup
     */
    function showInstallPopup() {
        if (!settings || !settings.pwa_enabled) return;
        
        const popup = document.getElementById('pwa-install-popup');
        if (popup) {
            popup.style.display = 'flex';
            popup.classList.add('pwa-popup-visible');
            
            // Update popup content from settings
            const titleEl = popup.querySelector('.pwa-popup-title');
            const descEl = popup.querySelector('.pwa-popup-description');
            const btnEl = popup.querySelector('.pwa-popup-install-btn');
            
            if (titleEl && settings.popup_title) titleEl.textContent = settings.popup_title;
            if (descEl && settings.popup_description) descEl.textContent = settings.popup_description;
            if (btnEl && settings.popup_button_text) btnEl.textContent = settings.popup_button_text;
            
            // Update state
            const state = getStoredState() || {};
            state.prompt_displayed = true;
            state.times_prompted = (state.times_prompted || 0) + 1;
            state.last_prompt_time = Date.now();
            saveState(state);
            
            analyticsData.install_prompt_displayed = true;
            sendAnalytics(analyticsData);
        }
    }

    /**
     * Show iOS installation guide
     */
    function showIOSGuide() {
        if (!settings || !settings.ios_guide_enabled) return;
        
        const guide = document.getElementById('pwa-ios-guide');
        if (guide) {
            guide.style.display = 'flex';
            guide.classList.add('pwa-popup-visible');
            
            const state = getStoredState() || {};
            state.prompt_displayed = true;
            state.times_prompted = (state.times_prompted || 0) + 1;
            state.last_prompt_time = Date.now();
            saveState(state);
            
            analyticsData.install_prompt_displayed = true;
            sendAnalytics(analyticsData);
        }
    }

    /**
     * Handle install button click
     */
    function handleInstallClick() {
        analyticsData.install_completed = false;
        
        if (deferredPrompt) {
            // Android Chrome - show native prompt
            deferredPrompt.prompt();
            
            deferredPrompt.userChoice.then(function(choiceResult) {
                if (choiceResult.outcome === 'accepted') {
                    analyticsData.install_completed = true;
                    isInstalled = true;
                    
                    const state = getStoredState() || {};
                    state.install_completed = true;
                    saveState(state);
                    
                    // Hide popup
                    const popup = document.getElementById('pwa-install-popup');
                    if (popup) {
                        popup.classList.remove('pwa-popup-visible');
                        setTimeout(function() {
                            popup.style.display = 'none';
                        }, 300);
                    }
                    
                    console.log('Glory2YahPub installed successfully!');
                } else {
                    analyticsData.install_completed = false;
                    analyticsData.dismissed = true;
                    
                    const state = getStoredState() || {};
                    state.dismissed = true;
                    state.dismissed_time = Date.now();
                    saveState(state);
                    
                    console.log('User declined installation');
                }
                
                deferredPrompt = null;
                sendAnalytics(analyticsData);
            });
        } else if (isIOSSafari()) {
            // On iOS, show the guide and mark as prompted
            analyticsData.install_completed = false;
            analyticsData.dismissed = false;
            
            const state = getStoredState() || {};
            state.install_completed = false;
            state.dismissed = false;
            state.prompt_displayed = true;
            saveState(state);
            
            sendAnalytics(analyticsData);
        }
    }

    /**
     * Dismiss/close the popup
     */
    function dismissPopup(popupId) {
        const popup = document.getElementById(popupId);
        if (popup) {
            popup.classList.remove('pwa-popup-visible');
            setTimeout(function() {
                popup.style.display = 'none';
            }, 300);
        }
        
        analyticsData.dismissed = true;
        sendAnalytics(analyticsData);
        
        const state = getStoredState() || {};
        state.dismissed = true;
        state.dismissed_time = Date.now();
        saveState(state);
    }

    // ===== EVENT HANDLERS =====

    /**
     * Handle beforeinstallprompt event (Android Chrome)
     */
    function handleBeforeInstallPrompt(e) {
        // Prevent the default mini-infobar
        e.preventDefault();
        
        // Store the event for later use
        deferredPrompt = e;
        
        // Show our custom popup
        const state = getStoredState() || {};
        if (state.prompt_displayed === false) {
            schedulePopup();
        }
    }

    /**
     * Handle app installed event
     */
    function handleAppInstalled() {
        isInstalled = true;
        analyticsData.install_completed = true;
        
        const state = getStoredState() || {};
        state.install_completed = true;
        saveState(state);
        
        // Hide any visible popups
        const popup = document.getElementById('pwa-install-popup');
        if (popup) {
            popup.style.display = 'none';
        }
        const guide = document.getElementById('pwa-ios-guide');
        if (guide) {
            guide.style.display = 'none';
        }
        
        sendAnalytics(analyticsData);
        console.log('Glory2YahPub app installed!');
    }

    /**
     * Schedule popup display with delay
     */
    function schedulePopup() {
        if (isInstalled) return;
        if (!shouldShowPrompt()) return;
        
        const delay = settings ? (settings.popup_delay_seconds || 5) * 1000 : CONFIG.POPUP_DELAY;
        
        setTimeout(function() {
            if (!isInstalled) {
                if (isIOSSafari()) {
                    showIOSGuide();
                } else {
                    showInstallPopup();
                }
            }
        }, delay);
    }

    /**
     * Schedule popup after user interaction
     */
    function schedulePopupAfterInteraction() {
        if (isInstalled) return;
        
        const state = getStoredState();
        if (state && state.prompt_displayed) return;
        
        setTimeout(function() {
            if (!isInstalled && shouldShowPrompt()) {
                if (isIOSSafari()) {
                    showIOSGuide();
                } else {
                    showInstallPopup();
                }
            }
        }, CONFIG.POPUP_DELAY_INTERACTION);
    }

    // ===== DOM SETUP =====

    /**
     * Set up all event listeners and initial state
     */
    function init() {
        // Check if already installed
        if (checkIfInstalled()) {
            console.log('Glory2YahPub already running as installed app');
            return;
        }

        // Update device info
        const deviceInfo = getDeviceInfo();
        analyticsData.device_type = deviceInfo.device_type;
        analyticsData.browser = deviceInfo.browser;
        analyticsData.os = deviceInfo.os;
        
        // Load settings from server
        loadSettings().then(function() {
            // Listen for beforeinstallprompt
            window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
            
            // Listen for app installed
            window.addEventListener('appinstalled', handleAppInstalled);
            
            // Set up popup close buttons
            document.addEventListener('click', function(e) {
                if (e.target.classList.contains('pwa-popup-close') ||
                    e.target.classList.contains('pwa-popup-overlay')) {
                    const popup = e.target.closest('.pwa-popup-wrapper');
                    if (popup) {
                        dismissPopup(popup.id);
                    }
                }
                
                // Handle install button click
                if (e.target.classList.contains('pwa-popup-install-btn')) {
                    handleInstallClick();
                }
                
                // Handle iOS guide close
                if (e.target.classList.contains('pwa-ios-close-btn')) {
                    dismissPopup('pwa-ios-guide');
                }
                
                // Handle iOS guide dismiss
                if (e.target.classList.contains('pwa-ios-dismiss-btn')) {
                    dismissPopup('pwa-ios-guide');
                }
            });
            
            // Schedule initial popup
            schedulePopup();
            
            // Also schedule after first user interaction
            const interactionEvents = ['click', 'touchstart', 'scroll', 'keydown'];
            function onFirstInteraction() {
                schedulePopupAfterInteraction();
                interactionEvents.forEach(function(event) {
                    document.removeEventListener(event, onFirstInteraction);
                });
            }
            interactionEvents.forEach(function(event) {
                document.addEventListener(event, onFirstInteraction, { once: true });
            });
            
            // Handle display mode changes (e.g., when installed)
            if (window.matchMedia) {
                const mediaQuery = window.matchMedia('(display-mode: standalone)');
                mediaQuery.addEventListener('change', function(e) {
                    if (e.matches) {
                        isInstalled = true;
                        analyticsData.install_completed = true;
                        sendAnalytics(analyticsData);
                    }
                });
            }
        });
    }

    // ===== START =====

    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
