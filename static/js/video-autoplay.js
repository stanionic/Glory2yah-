/**
 * Enhanced Video Autoplay System for Glory2YahPub
 * Handles intelligent video autoplay with viewport detection
 */

class VideoAutoplayManager {
    constructor() {
        this.videos = [];
        this.observer = null;
        this.init();
    }

    init() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setup());
        } else {
            this.setup();
        }
    }

    setup() {
        // Find all video elements
        this.videos = Array.from(document.querySelectorAll('video[data-autoplay]'));
        
        // Setup Intersection Observer for viewport detection
        this.setupIntersectionObserver();
        
        // Setup event listeners for each video
        this.videos.forEach(video => this.setupVideoListeners(video));
        
        // Initial check for videos in viewport
        this.checkVideosInViewport();
    }

    setupIntersectionObserver() {
        const options = {
            root: null,
            rootMargin: '0px',
            threshold: 0.5 // Video must be 50% visible
        };

        this.observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                const video = entry.target;
                
                if (entry.isIntersecting) {
                    // Video is in viewport
                    this.playVideo(video);
                } else {
                    // Video is out of viewport
                    this.pauseVideo(video);
                }
            });
        }, options);

        // Observe all videos
        this.videos.forEach(video => this.observer.observe(video));
    }

    setupVideoListeners(video) {
        // Add loading indicator
        video.addEventListener('loadstart', () => {
            this.showLoadingIndicator(video);
        });

        video.addEventListener('canplay', () => {
            this.hideLoadingIndicator(video);
        });

        // Hover to unmute (optional)
        video.addEventListener('mouseenter', () => {
            if (video.hasAttribute('data-hover-unmute')) {
                video.muted = false;
            }
        });

        video.addEventListener('mouseleave', () => {
            if (video.hasAttribute('data-hover-unmute')) {
                video.muted = true;
            }
        });

        // Click to toggle play/pause
        video.addEventListener('click', (e) => {
            if (!video.hasAttribute('data-no-click-toggle')) {
                e.stopPropagation();
                this.togglePlayPause(video);
            }
        });

        // Error handling
        video.addEventListener('error', (e) => {
            console.error('Video error:', e);
            this.showErrorIndicator(video);
        });

        // Loop handling
        video.addEventListener('ended', () => {
            if (video.hasAttribute('data-loop')) {
                video.currentTime = 0;
                this.playVideo(video);
            }
        });
    }

    async playVideo(video) {
        try {
            // Ensure video is muted for autoplay (browser requirement)
            video.muted = true;
            
            // Attempt to play
            await video.play();
            
            // Add playing class for styling
            video.classList.add('video-playing');
            video.classList.remove('video-paused');
        } catch (error) {
            console.warn('Autoplay prevented:', error);
            // Show play button overlay if autoplay fails
            this.showPlayButton(video);
        }
    }

    pauseVideo(video) {
        if (!video.paused) {
            video.pause();
            video.classList.remove('video-playing');
            video.classList.add('video-paused');
        }
    }

    togglePlayPause(video) {
        if (video.paused) {
            this.playVideo(video);
        } else {
            this.pauseVideo(video);
        }
    }

    showLoadingIndicator(video) {
        const container = video.parentElement;
        if (!container.querySelector('.video-loading')) {
            const loader = document.createElement('div');
            loader.className = 'video-loading';
            loader.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            container.style.position = 'relative';
            container.appendChild(loader);
        }
    }

    hideLoadingIndicator(video) {
        const container = video.parentElement;
        const loader = container.querySelector('.video-loading');
        if (loader) {
            loader.remove();
        }
    }

    showPlayButton(video) {
        const container = video.parentElement;
        if (!container.querySelector('.video-play-overlay')) {
            const overlay = document.createElement('div');
            overlay.className = 'video-play-overlay';
            overlay.innerHTML = '<i class="fas fa-play-circle"></i>';
            overlay.addEventListener('click', (e) => {
                e.stopPropagation();
                this.playVideo(video);
                overlay.remove();
            });
            container.style.position = 'relative';
            container.appendChild(overlay);
        }
    }

    showErrorIndicator(video) {
        const container = video.parentElement;
        const error = document.createElement('div');
        error.className = 'video-error';
        error.innerHTML = '<i class="fas fa-exclamation-triangle"></i><p>Erè nan chajman videyo</p>';
        container.appendChild(error);
    }

    checkVideosInViewport() {
        // Initial check for videos already in viewport
        this.videos.forEach(video => {
            const rect = video.getBoundingClientRect();
            const isInViewport = (
                rect.top >= 0 &&
                rect.left >= 0 &&
                rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                rect.right <= (window.innerWidth || document.documentElement.clientWidth)
            );

            if (isInViewport) {
                this.playVideo(video);
            }
        });
    }

    // Public method to refresh video list (useful for dynamically added videos)
    refresh() {
        this.videos = Array.from(document.querySelectorAll('video[data-autoplay]'));
        this.videos.forEach(video => {
            if (!this.observer) return;
            this.observer.observe(video);
            this.setupVideoListeners(video);
        });
    }

    // Cleanup method
    destroy() {
        if (this.observer) {
            this.observer.disconnect();
        }
        this.videos.forEach(video => {
            this.pauseVideo(video);
        });
    }
}

// Initialize the video autoplay manager
let videoManager;

// Auto-initialize when script loads
if (typeof window !== 'undefined') {
    videoManager = new VideoAutoplayManager();
    
    // Expose globally for manual control if needed
    window.VideoAutoplayManager = VideoAutoplayManager;
    window.videoManager = videoManager;
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = VideoAutoplayManager;
}
