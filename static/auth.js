/**
 * Authentication utilities for JWT token handling
 */

// Token management functions
const auth = {
    /**
     * Store authentication tokens in localStorage
     * @param {string} accessToken - The JWT access token
     * @param {string} refreshToken - The JWT refresh token
     * @param {number} expiresIn - Expiration time in seconds
     */
    setTokens(accessToken, refreshToken, expiresIn) {
        localStorage.setItem('access_token', accessToken);
        localStorage.setItem('refresh_token', refreshToken);
        
        // Calculate expiration timestamp
        const expiresAt = new Date().getTime() + expiresIn * 1000;
        localStorage.setItem('expires_at', expiresAt.toString());
    },
    
    /**
     * Get the stored access token
     * @returns {string|null} The access token or null if not found
     */
    getAccessToken() {
        return localStorage.getItem('access_token');
    },
    
    /**
     * Get the stored refresh token
     * @returns {string|null} The refresh token or null if not found
     */
    getRefreshToken() {
        return localStorage.getItem('refresh_token');
    },
    
    /**
     * Clear all authentication tokens from storage
     */
    clearTokens() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('expires_at');
    },
    
    /**
     * Check if user is logged in with a valid token
     * @returns {boolean} True if logged in, false otherwise
     */
    isLoggedIn() {
        const token = this.getAccessToken();
        return !!token && !this.isTokenExpired();
    },
    
    /**
     * Check if the current token is expired
     * @returns {boolean} True if token is expired, false otherwise
     */
    isTokenExpired() {
        const expiresAt = localStorage.getItem('expires_at');
        if (!expiresAt) return true;
        
        return new Date().getTime() > parseInt(expiresAt, 10);
    },
    
    /**
     * Get authorization headers for API requests
     * @returns {Object} Headers object with Authorization header
     */
    getAuthHeaders() {
        const token = this.getAccessToken();
        return {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        };
    },
    
    /**
     * Try to refresh the access token using the refresh token
     * @returns {Promise<boolean>} True if refresh succeeded, false otherwise
     */
    async refreshToken() {
        try {
            const refreshToken = this.getRefreshToken();
            if (!refreshToken) return false;
            
            const response = await fetch('/api/auth/refresh', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ refresh_token: refreshToken })
            });
            
            if (response.ok) {
                const data = await response.json();
                localStorage.setItem('access_token', data.access_token);
                
                // Calculate expiration timestamp
                const expiresAt = new Date().getTime() + data.expires_in * 1000;
                localStorage.setItem('expires_at', expiresAt.toString());
                
                return true;
            }
            
            return false;
        } catch (error) {
            console.error('Token refresh failed:', error);
            return false;
        }
    },
    
    /**
     * Initialize authentication by checking token and setting up refresh timer
     */
    init() {
        // Check for token in URL (for redirects from other services)
        const urlParams = new URLSearchParams(window.location.search);
        const accessToken = urlParams.get('access_token');
        const refreshToken = urlParams.get('refresh_token');
        const expiresIn = urlParams.get('expires_in');
        
        if (accessToken && refreshToken && expiresIn) {
            this.setTokens(accessToken, refreshToken, expiresIn);
            
            // Clean up URL
            window.history.replaceState({}, document.title, window.location.pathname);
        }
        
        // Set up refresh timer if logged in
        if (this.isLoggedIn()) {
            this.setupRefreshTimer();
        }
    },
    
    /**
     * Set up a timer to refresh the token before it expires
     */
    setupRefreshTimer() {
        const expiresAt = localStorage.getItem('expires_at');
        if (!expiresAt) return;
        
        const expiresIn = parseInt(expiresAt, 10) - new Date().getTime();
        
        // Refresh 1 minute before expiration
        const refreshTime = Math.max(0, expiresIn - 60000);
        
        setTimeout(async () => {
            const refreshed = await this.refreshToken();
            if (refreshed) {
                this.setupRefreshTimer();
            }
        }, refreshTime);
    },
    
    /**
     * Make an authenticated API request
     * @param {string} url - The API endpoint URL
     * @param {Object} options - Fetch options (method, body, etc.)
     * @returns {Promise<Object>} The API response data
     */
    async apiRequest(url, options = {}) {
        // Check if token is expired and try to refresh if needed
        if (this.isTokenExpired()) {
            const refreshed = await this.refreshToken();
            if (!refreshed) {
                // Redirect to login if refresh failed
                window.location.href = '/login';
                return null;
            }
        }
        
        // Add authorization headers
        const headers = {
            ...options.headers,
            ...this.getAuthHeaders()
        };
        
        try {
            const response = await fetch(url, {
                ...options,
                headers
            });
            
            if (response.status === 401) {
                // Try to refresh token if unauthorized
                const refreshed = await this.refreshToken();
                if (refreshed) {
                    // Retry request with new token
                    return this.apiRequest(url, options);
                } else {
                    // Redirect to login if refresh failed
                    window.location.href = '/login';
                    return null;
                }
            }
            
            return await response.json();
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }
};

// Initialize auth when the page loads
document.addEventListener('DOMContentLoaded', () => {
    auth.init();
});

// Export the auth object
window.auth = auth; 