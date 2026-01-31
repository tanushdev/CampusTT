const API_BASE_URL = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1')
    ? 'http://localhost:5000/api/v1'
    : '/api/v1';
const THEME_KEY = 'campusiq_theme';

function initTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    setTheme(saved || (prefersDark ? 'dark' : 'light'));
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    setTheme(current === 'dark' ? 'light' : 'dark');
}

// ============================================
// Initialize
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initAnimations();
    checkAuthCallback();
    checkAuthStatus(); // Check if already logged in for index.html UI
});

async function checkAuthStatus() {
    const token = localStorage.getItem('campusiq_token');
    if (!token) return;

    // Detect if we are on index.html
    const authNav = document.getElementById('auth-nav');
    const authHero = document.getElementById('auth-hero');
    if (!authNav && !authHero) return;

    try {
        const response = await fetch(`${API_BASE_URL}/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const result = await response.json();

        if (result.success) {
            const role = result.data.role.code;
            const redirects = {
                'SUPER_ADMIN': 'super-admin-dashboard.html',
                'COLLEGE_ADMIN': 'college-admin-dashboard.html',
                'FACULTY': 'dashboard.html',
                'STAFF': 'dashboard.html',
                'STUDENT': 'dashboard.html'
            };
            const dashboardUrl = redirects[role] || 'dashboard.html';

            if (authNav) {
                authNav.innerHTML = `<a href="${dashboardUrl}" class="btn btn-dark btn-pill">Dashboard</a>`;
            }
            if (authHero) {
                authHero.innerHTML = `<a href="${dashboardUrl}" class="btn btn-dark btn-pill join-btn">MY PANEL</a>`;
            }
            const searchInput = document.getElementById('home-search-input');
            if (searchInput) {
                searchInput.onfocus = () => window.location.href = dashboardUrl;
                searchInput.placeholder = "Go to dashboard to search...";
            }
        }
    } catch (err) {
        console.error('Auth check failed:', err);
    }
}

function checkAuthCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const accessToken = urlParams.get('access_token');
    const refreshToken = urlParams.get('refresh_token');
    const userId = urlParams.get('user_id');

    if (accessToken && userId) {
        localStorage.setItem('campusiq_token', accessToken);
        if (refreshToken) localStorage.setItem('campusiq_refresh_token', refreshToken);
        localStorage.setItem('campusiq_user_id', userId);

        // Clear query parameters from URL for a cleaner look
        window.history.replaceState({}, document.title, window.location.pathname);

        // Show success
        showNotification('Successfully logged in with Google!', 'success');

        // Fetch user profile to determine where to redirect
        fetchUserInfoAndRedirect();
    }
}

async function fetchUserInfoAndRedirect() {
    try {
        const response = await fetch(`${API_BASE_URL}/auth/me`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('campusiq_token')}`
            }
        });

        const result = await response.json();

        if (result.success) {
            const user = result.data;
            const role = user.role.code;

            // Redirect after a short delay so user can see notification
            setTimeout(() => {
                const redirects = {
                    'SUPER_ADMIN': 'super-admin-dashboard.html',
                    'COLLEGE_ADMIN': 'college-admin-dashboard.html',
                    'FACULTY': 'dashboard.html',
                    'STAFF': 'dashboard.html',
                    'STUDENT': 'dashboard.html'
                };
                window.location.href = redirects[role] || 'dashboard.html';
            }, 1000);
        } else {
            console.error('Profile fetch failed:', result);
            // Default to main dashboard if profile fetch fails
            setTimeout(() => { window.location.href = 'dashboard.html'; }, 1000);
        }
    } catch (err) {
        console.error('Profile Fetch Error:', err);
        setTimeout(() => { window.location.href = 'dashboard.html'; }, 1000);
    }
}

function initAnimations() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.feature-card, .stat-item, .example-item').forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition = 'all 0.5s ease';
        observer.observe(el);
    });
}

// ============================================
// Modal Functions
// ============================================
function showLoginModal() {
    document.getElementById('login-modal').classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
    document.body.style.overflow = '';
}

// Close on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal.active').forEach(m => m.classList.remove('active'));
        document.body.style.overflow = '';
    }
});

// ============================================
// Auth Functions
// ============================================
function loginWithGoogle() {
    // Redirect to backend Google OAuth flow:
    window.location.href = `${API_BASE_URL}/auth/google/login`;
}

function handleLogin(event) {
    event.preventDefault();
    showNotification('Email login is currently for demo. Use Google Login for the real flow!', 'info');
}

// ============================================
// Navigation
// ============================================
function scrollToSection(id) {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth' });
}

// ============================================
// QnA Chat
// ============================================

function askQuestion(q) {
    document.getElementById('qna-input').value = q;
    sendQuestion();
}

function handleKeyPress(e) {
    if (e.key === 'Enter') sendQuestion();
}

async function sendQuestion() {
    const input = document.getElementById('qna-input');
    const q = input.value.trim();
    if (!q) return;

    const chat = document.getElementById('chat-messages');

    // User message
    chat.innerHTML += `
        <div class="message user">
            <div class="message-avatar">👤</div>
            <div class="message-bubble"><p>${escapeHtml(q)}</p></div>
        </div>
    `;
    input.value = '';
    chat.scrollTop = chat.scrollHeight;

    // Show typing indicator
    const botMsgId = 'bot-msg-' + Date.now();
    chat.innerHTML += `
        <div class="message bot" id="${botMsgId}">
            <div class="message-avatar">🤖</div>
            <div class="message-bubble">
                <p><i class="fas fa-circle-notch fa-spin"></i> Analyzing campus data...</p>
            </div>
        </div>
    `;
    chat.scrollTop = chat.scrollHeight;

    const botMsg = document.getElementById(botMsgId);
    const token = localStorage.getItem('campusiq_token');

    // Mock response logic for demo & failed connections
    const getMockResponse = (query) => {
        const q = query.toLowerCase();
        if (q.includes('free') || q.includes('room')) {
            return "Based on the live schedule, Level 4 (Room 401, 403) and the Central Lab are currently unoccupied.";
        }
        if (q.includes('teach') || q.includes('who') || q.includes('professor')) {
            return "Big Data Analytics is taught by Dr. Rajesh Sharma, while Network Security is handled by Prof. Anita Iyer.";
        }
        if (q.includes('schedule') || q.includes('today')) {
            return "Today is a busy day! You have 6 scheduled sessions in COMP Dept including a 2-hour Lab for Cloud Computing starting at 1:00 PM.";
        }
        return "I can help you navigate campus schedules and faculty info. For live personal data, please login with your Google account!";
    };

    try {
        if (!token) {
            // Simulated delay for realism
            await new Promise(r => setTimeout(r, 1500));
            botMsg.querySelector('.message-bubble').innerHTML = `<p>${getMockResponse(q)}</p>`;
            chat.scrollTop = chat.scrollHeight;
            return;
        }

        const response = await fetch(`${API_BASE_URL}/qna/ask`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ query: q })
        });

        const data = await response.json();
        if (data.success) {
            botMsg.querySelector('.message-bubble').innerHTML = `<p>${data.data.response}</p>`;
        } else {
            botMsg.querySelector('.message-bubble').innerHTML = `<p>${getMockResponse(q)}</p> <p style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.5rem;">(Note: Live sync error - showing demo data)</p>`;
        }
    } catch (err) {
        console.error('QnA Error:', err);
        botMsg.querySelector('.message-bubble').innerHTML = `<p>${getMockResponse(q)}</p> <p style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.5rem;">(Note: Server connection offline - showing demo data)</p>`;
    }
    chat.scrollTop = chat.scrollHeight;
}

// ============================================
// Utilities
// ============================================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showNotification(msg, type = 'info') {
    const colors = { info: '#3b82f6', success: '#22c55e', error: '#ef4444' };
    const n = document.createElement('div');
    n.style.cssText = `
        position:fixed;top:80px;right:20px;z-index:9999;
        padding:1rem 1.5rem;border-radius:10px;
        background:${colors[type]};color:#fff;font-size:0.9rem;
        box-shadow:0 10px 30px rgba(0,0,0,0.2);
        animation:slideIn 0.3s ease;
    `;
    n.innerHTML = `${msg} <button onclick="this.parentElement.remove()" style="background:none;border:none;color:#fff;cursor:pointer;margin-left:1rem;">×</button>`;
    document.body.appendChild(n);
    setTimeout(() => n.remove(), 4000);
}

// Styles
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn { from{transform:translateX(100%);opacity:0} to{transform:translateX(0);opacity:1} }
    .res-list { list-style:none; padding:0; margin:0.5rem 0 0; }
    .res-list li { padding:0.4rem 0.6rem; margin-bottom:0.25rem; background:var(--bg-secondary); border-radius:6px; font-size:0.8rem; color:var(--text-secondary); }
    .message.user .res-list li { background:rgba(255,255,255,0.15); color:#fff; }
`;
document.head.appendChild(style);
