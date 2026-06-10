document.addEventListener('DOMContentLoaded', function() {
    // Carousel functionality
    const carouselTrack = document.getElementById('carouselTrack');
    const carouselCards = document.querySelectorAll('.carousel-card');
    const prevButton = document.querySelector('.carousel-prev');
    const nextButton = document.querySelector('.carousel-next');
    const indicatorsContainer = document.getElementById('carouselIndicators');

    if (carouselTrack) {
        let currentIndex = 0;
        const totalCards = carouselCards.length;

        // Create indicators
        for (let i = 0; i < totalCards; i++) {
            const indicator = document.createElement('div');
            indicator.classList.add('carousel-indicator');
            if (i === 0) {
                indicator.classList.add('active');
            }
            indicator.addEventListener('click', () => {
                goToSlide(i);
            });
            indicatorsContainer.appendChild(indicator);
        }

        const indicators = document.querySelectorAll('.carousel-indicator');

        function updateCarousel() {
            const offset = -currentIndex * 100;
            carouselTrack.style.transform = `translateX(${offset}%)`;
            indicators.forEach((indicator, index) => {
                indicator.classList.toggle('active', index === currentIndex);
            });
        }

        function goToSlide(index) {
            currentIndex = index;
            updateCarousel();
        }

        if (prevButton) {
            prevButton.addEventListener('click', () => {
                currentIndex = (currentIndex > 0) ? currentIndex - 1 : totalCards - 1;
                updateCarousel();
            });
        }

        if (nextButton) {
            nextButton.addEventListener('click', () => {
                currentIndex = (currentIndex < totalCards - 1) ? currentIndex + 1 : 0;
                updateCarousel();
            });
        }
    }

    // Media type selector in submit_ad.html
    const mediaTypeRadios = document.querySelectorAll('input[name="media_type"]');
    const imagesSection = document.getElementById('images-section');
    const videoSection = document.getElementById('video-section');
    const imageInputs = document.querySelectorAll('#images-section input[type="file"]');
    const videoInput = document.querySelector('#video-section input[type="file"]');

    if (mediaTypeRadios.length > 0) {
        function toggleMediaSections() {
            const selectedMediaType = document.querySelector('input[name="media_type"]:checked').value;
            if (selectedMediaType === 'images') {
                imagesSection.style.display = 'block';
                videoSection.style.display = 'none';
                imageInputs.forEach(input => input.required = true);
                videoInput.required = false;
            } else {
                imagesSection.style.display = 'none';
                videoSection.style.display = 'block';
                imageInputs.forEach(input => input.required = false);
                videoInput.required = true;
            }
        }

        mediaTypeRadios.forEach(radio => {
            radio.addEventListener('change', toggleMediaSections);
        });

        toggleMediaSections(); // Initial call
    }
});

function moveCarousel(direction) {
    const track = document.getElementById('carouselTrack');
    const indicators = document.querySelectorAll('.carousel-indicator');
    let currentIndex = parseInt(track.dataset.currentIndex || '0');
    const totalItems = track.children.length;

    currentIndex += direction;

    if (currentIndex < 0) {
        currentIndex = totalItems - 1;
    } else if (currentIndex >= totalItems) {
        currentIndex = 0;
    }

    track.style.transform = `translateX(-${currentIndex * 100}%)`;
    track.dataset.currentIndex = currentIndex;

    indicators.forEach((indicator, index) => {
        indicator.classList.toggle('active', index === currentIndex);
    });
}
