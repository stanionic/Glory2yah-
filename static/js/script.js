document.addEventListener('DOMContentLoaded', function() {
    const descriptionTextarea = document.getElementById('description');
    if (descriptionTextarea) {
        const charCount = document.createElement('div');
        charCount.className = 'char-count';
        charCount.style.textAlign = 'right';
        charCount.style.marginTop = '5px';
        charCount.style.color = '#666';
        descriptionTextarea.parentNode.appendChild(charCount);

        function updateCharCount() {
            const remaining = 300 - descriptionTextarea.value.length;
            charCount.textContent = `${remaining} karaktè rete`;

            if (remaining < 50) {
                charCount.style.color = '#dc3545';
            } else if (remaining < 100) {
                charCount.style.color = '#ffc107';
            } else {
                charCount.style.color = '#666';
            }
        }

        descriptionTextarea.addEventListener('input', updateCharCount);
        updateCharCount();
    }

    const uploadBoxes = document.querySelectorAll('.upload-box');
    uploadBoxes.forEach(box => {
        const span = box.querySelector('span');
        const input = box.querySelector('input[type="file"]');
        if (span && input) {
            span.addEventListener('click', () => {
                input.click();
            });
        }
    });

    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        input.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    const preview = document.createElement('img');
                    preview.src = e.target.result;
                    preview.style.maxWidth = '100px';
                    preview.style.maxHeight = '100px';
                    preview.style.marginTop = '10px';

                    const existingPreview = input.parentNode.querySelector('img');
                    if (existingPreview) {
                        existingPreview.remove();
                    }

                    input.parentNode.appendChild(preview);
                };
                reader.readAsDataURL(file);
            }
        });
    });

    // Gkach price calculation
    const priceGourdesInput = document.getElementById('price_gourdes');
    const priceGkachInput = document.getElementById('price_gkach');
    const gkachEquivalentDiv = document.getElementById('gkach-equivalent');
    const gkachPriceSpan = document.getElementById('gkach-price');

    if (priceGourdesInput && priceGkachInput && gkachEquivalentDiv && gkachPriceSpan) {
        let currentRate = 50; // Default rate

        // Fetch current Gkach rate
        fetch('/api/gkach_rate')
            .then(response => response.json())
            .then(data => {
                currentRate = data.rate;
                console.log('Fetched Gkach rate:', currentRate, data.currency);
            })
            .catch(error => {
                console.error('Error fetching Gkach rate:', error);
            });

        function updateGkachPrice() {
            const gourdesValue = parseFloat(priceGourdesInput.value);
            if (!isNaN(gourdesValue) && gourdesValue > 0) {
                const gkachValue = Math.ceil(gourdesValue / currentRate);
                priceGkachInput.value = gkachValue;
                gkachPriceSpan.textContent = gkachValue;
                gkachEquivalentDiv.style.display = 'block';
            } else {
                gkachEquivalentDiv.style.display = 'none';
                priceGkachInput.value = '0';
            }
        }

        priceGourdesInput.addEventListener('input', updateGkachPrice);
        // Initial calculation if there's a value
        if (priceGourdesInput.value) {
            updateGkachPrice();
        }
    }
});

function formatWhatsAppNumber(input) {
    let value = input.value.replace(/\D/g, '');
    if (value.startsWith('509')) {
        value = '+' + value;
    } else if (!value.startsWith('+')) {
        value = '+509' + value;
    }
    input.value = value;
}

function copyLink() {
    const shareUrl = window.location.href;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(shareUrl).then(() => {
            alert('Lyen kopye nan clipboard!');
        }).catch(err => {
            console.error('Erè nan kopye lyen:', err);
            fallbackCopyTextToClipboard(shareUrl);
        });
    } else {
        fallbackCopyTextToClipboard(shareUrl);
    }
}

function fallbackCopyTextToClipboard(text) {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-999999px";
    textArea.style.top = "-999999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
        const successful = document.execCommand('copy');
        if (successful) {
            alert('Lyen kopye nan clipboard!');
        } else {
            alert('Erè nan kopye lyen.');
        }
    } catch (err) {
        console.error('Erè nan kopye lyen:', err);
        alert('Erè nan kopye lyen.');
    }
    document.body.removeChild(textArea);
}

function copyBatchLink(batchId) {
    const batchUrl = `${window.location.origin}/batch/${batchId}`;
    navigator.clipboard.writeText(batchUrl).then(() => {
        alert('Lyen gwoup kopye nan clipboard!');
    }).catch(err => {
        console.error('Erè nan kopye lyen:', err);
        alert('Erè nan kopye lyen.');
    });
}

function showAdModal(adId, images, description) {
    const imageList = images.split(',');
    const modalImages = document.getElementById('modal-images');
    const modalDescription = document.getElementById('modal-description');

    modalImages.innerHTML = '';
    imageList.forEach(img => {
        const imgElement = document.createElement('img');
        imgElement.src = `/static/uploads/${img}`;
        imgElement.alt = 'Piblisite Imaj';
        imgElement.style.maxWidth = '100%';
        imgElement.style.marginBottom = '10px';
        modalImages.appendChild(imgElement);
    });

    modalDescription.innerHTML = `<p>${description}</p>`;

    document.getElementById('ad-modal').style.display = 'block';
}

function closeAdModal() {
    document.getElementById('ad-modal').style.display = 'none';
}

// Autoplay carousel
document.addEventListener('DOMContentLoaded', function() {
    const carousel = document.getElementById('batch-carousel');
    if (carousel) {
        const cards = carousel.querySelectorAll('.whatsapp-ad-card');
        if (cards.length > 0) {
            const cardWidth = cards[0].offsetWidth + 16; // 16 for gap
            let currentIndex = 0;

            setInterval(() => {
                currentIndex = (currentIndex + 1) % cards.length;
                carousel.scrollLeft = currentIndex * cardWidth;
            }, 1000); // 1 second per ad
        }
    }
});
