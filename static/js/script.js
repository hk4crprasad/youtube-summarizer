// YouTube Summarizer Custom JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
    
    // Initialize clipboard.js for copy buttons
    if (typeof ClipboardJS !== 'undefined') {
        const clipboard = new ClipboardJS('.copy-btn');
        
        clipboard.on('success', function(e) {
            // Change button text temporarily
            const originalText = e.trigger.innerHTML;
            e.trigger.innerHTML = '<i class="fas fa-check me-1"></i> Copied!';
            
            // Reset button text after 2 seconds
            setTimeout(function() {
                e.trigger.innerHTML = originalText;
            }, 2000);
            
            e.clearSelection();
        });
        
        clipboard.on('error', function(e) {
            console.error('Error copying text:', e);
            // Show error message
            const originalText = e.trigger.innerHTML;
            e.trigger.innerHTML = '<i class="fas fa-times me-1"></i> Error!';
            
            // Reset button text after 2 seconds
            setTimeout(function() {
                e.trigger.innerHTML = originalText;
            }, 2000);
        });
    }
    
    // YouTube URL validation for the form
    const youtubeForm = document.getElementById('youtube-form');
    if (youtubeForm) {
        youtubeForm.addEventListener('submit', function(e) {
            const urlInput = document.getElementById('youtube_url');
            if (urlInput && !isValidYouTubeUrl(urlInput.value)) {
                e.preventDefault();
                alert('Please enter a valid YouTube URL');
                urlInput.focus();
            }
        });
    }
    
    // API key copy functionality
    const apiKeyCopyBtns = document.querySelectorAll('.api-key-copy');
    apiKeyCopyBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const keyElement = this.closest('.api-key-card').querySelector('.key-value');
            if (keyElement) {
                navigator.clipboard.writeText(keyElement.textContent.trim())
                    .then(() => {
                        // Success message
                        const originalText = this.innerHTML;
                        this.innerHTML = '<i class="fas fa-check me-1"></i> Copied!';
                        setTimeout(() => {
                            this.innerHTML = originalText;
                        }, 2000);
                    })
                    .catch(err => {
                        console.error('Could not copy text: ', err);
                    });
            }
        });
    });
    
    // Password confirmation validation
    const passwordForm = document.getElementById('password-form');
    if (passwordForm) {
        passwordForm.addEventListener('submit', function(e) {
            const newPassword = document.getElementById('new_password');
            const confirmPassword = document.getElementById('confirm_password');
            
            if (newPassword && confirmPassword && newPassword.value !== confirmPassword.value) {
                e.preventDefault();
                alert('Passwords do not match!');
                confirmPassword.focus();
            }
        });
    }
});

// Helper function to validate YouTube URLs
function isValidYouTubeUrl(url) {
    const pattern = /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.?be)\/.+$/;
    return pattern.test(url);
}

// Toggle between light and dark mode
function toggleDarkMode() {
    const body = document.body;
    const isDarkMode = body.classList.toggle('dark-mode');
    
    // Store user preference
    localStorage.setItem('darkMode', isDarkMode);
    
    // Update button icon
    const darkModeBtn = document.getElementById('dark-mode-toggle');
    if (darkModeBtn) {
        darkModeBtn.innerHTML = isDarkMode 
            ? '<i class="fas fa-sun"></i>' 
            : '<i class="fas fa-moon"></i>';
    }
}

// Check for saved user preference on page load
function initializeDarkMode() {
    const savedDarkMode = localStorage.getItem('darkMode');
    if (savedDarkMode === 'true') {
        document.body.classList.add('dark-mode');
        const darkModeBtn = document.getElementById('dark-mode-toggle');
        if (darkModeBtn) {
            darkModeBtn.innerHTML = '<i class="fas fa-sun"></i>';
        }
    }
}

// Initialize dark mode
initializeDarkMode();
