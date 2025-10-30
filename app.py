from flask import Flask, request, redirect, session, render_template_string, jsonify, url_for
import requests
from urllib.parse import urlencode
import secrets
import os
import json
import re

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Config file to store credentials
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'spotify_config.json')

def load_config():
    """Load credentials from config file"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return None

def save_config(client_id, client_secret):
    """Save credentials to config file"""
    config = {
        'client_id': client_id,
        'client_secret': client_secret
    }
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)
    return config

def get_credentials():
    """Get credentials from config file or environment variables"""
    config = load_config()
    if config:
        return config['client_id'], config['client_secret']
    
    # Fallback to environment variables
    client_id = os.environ.get('SPOTIFY_CLIENT_ID')
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
    
    if client_id and client_secret:
        return client_id, client_secret
    
    return None, None

REDIRECT_URI = 'http://127.0.0.1:5000/callback'
SCOPES = 'user-library-read playlist-read-private playlist-read-collaborative user-read-private user-read-email'

# ------------------------------
# Heuristic license classifier
# ------------------------------
POSITIVE_LICENSE_KEYWORDS = [
    'royalty free', 'royalty-free', 'free to use', 'free use', 'creative commons',
    'cc0', 'cc 0', 'public domain', 'no copyright', 'copyright free',
    'free for commercial', 'free for monetization', 'youtube safe', 'license free',
    'ncs', 'nocopyrightsounds', 'chillhop records', 'chillhop music', 'copyright-free'
]

NEGATIVE_LICENSE_KEYWORDS = [
    '©', '℗', '(c) ', '(p) ', 'all rights reserved', 'under exclusive license',
    'exclusive license', 'licensed to', 'unauthorized', 'broadcast prohibited',
    'for promotional use only', 'not for resale', 'umg', 'universal music', 'sony',
    'warner', 'wmg', 'wmg', 'smE', 'sony music entertainment', 'wmg', 'atlantic records',
    'columbia records', 'rca records', 'def jam', 'republic records', 'interscope'
]

# Labels/brands that usually publish copyright-free music (heuristic; user-driven)
POSITIVE_LABELS = {
    'ncs',
    'nocopyrightsounds',
    'chillhop records',
    'chillhop music'
}

def _normalize_text(value):
    if not value:
        return ''
    if isinstance(value, (list, tuple)):
        return ' '.join(_normalize_text(v) for v in value)
    return str(value).lower()

def classify_license_from_metadata(*texts):
    """Simple keyword-based check. Returns dict with is_free, confidence, signals, reason."""
    blob = _normalize_text(list(texts))
    positives = [kw for kw in POSITIVE_LICENSE_KEYWORDS if kw in blob]
    negatives = [kw for kw in NEGATIVE_LICENSE_KEYWORDS if kw in blob]

    # Special handling: if a positive label appears anywhere, treat as strong positive
    positive_label_hit = any(lbl in blob for lbl in POSITIVE_LABELS)

    # Scoring: negatives weigh 1 normally, but if a positive label is present, negatives weigh 0.5
    negative_weight = 0.5 if positive_label_hit else 1.0
    score = len(positives) - (negative_weight * len(negatives))
    is_free = score > 0 or positive_label_hit

    # Confidence heuristic (rebased):
    # - Strong when positive label hit
    # - Medium when clear positives present without many negatives
    # - Low-medium when no signals
    total_signals = len(positives) + len(negatives)
    if positive_label_hit:
        confidence = 0.9 if is_free else 0.7
    elif total_signals == 0:
        confidence = 0.4
    else:
        base = 0.55 + 0.08 * (len(positives)) - 0.05 * (len(negatives))
        confidence = max(0.35, min(0.9, base))

    reason = 'No clear signals detected.' if not (positives or negatives or positive_label_hit) else \
        f"Signals → positive: {', '.join(positives) if positives else ('label whitelisted' if positive_label_hit else 'none')}; " \
        f"negative: {', '.join(negatives) if negatives else 'none'}."

    return {
        'is_free': bool(is_free),
        'confidence': round(confidence, 2),
        'signals': {
            'positive': positives + (['label match'] if positive_label_hit else []),
            'negative': negatives
        },
        'reason': reason
    }

# HTML Templates
SETUP_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Setup - Spotify Copyright Checker</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1DB954 0%, #191414 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            max-width: 600px;
            width: 100%;
        }
        h1 {
            color: #191414;
            margin-bottom: 10px;
            font-size: 2em;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
        }
        .step {
            background: #f5f5f5;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            border-left: 4px solid #1DB954;
        }
        .step-number {
            background: #1DB954;
            color: white;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            margin-right: 10px;
        }
        .step-title {
            font-weight: bold;
            margin-bottom: 10px;
            font-size: 18px;
        }
        .step-content {
            color: #555;
            line-height: 1.6;
        }
        .step-content a {
            color: #1DB954;
            text-decoration: none;
            font-weight: bold;
        }
        .step-content a:hover {
            text-decoration: underline;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: #333;
            font-weight: bold;
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input:focus {
            outline: none;
            border-color: #1DB954;
        }
        .btn {
            background: #1DB954;
            color: white;
            border: none;
            padding: 15px 40px;
            border-radius: 30px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            width: 100%;
        }
        .btn:hover {
            background: #1ed760;
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(29, 185, 84, 0.4);
        }
        .info-box {
            background: #e8f5e9;
            border-left: 4px solid #1DB954;
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
        }
        .warning-box {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
        }
        .code {
            background: #f5f5f5;
            padding: 3px 8px;
            border-radius: 3px;
            font-family: monospace;
            color: #d63384;
        }
        .error {
            color: #dc3545;
            background: #f8d7da;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .success {
            color: #155724;
            background: #d4edda;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔧 Setup Spotify App</h1>
        <p class="subtitle">Configure your Spotify Developer credentials</p>

        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}

        <div class="step">
            <div class="step-title">
                <span class="step-number">1</span>
                Create a Spotify Developer App
            </div>
            <div class="step-content">
                1. Go to <a href="https://developer.spotify.com/dashboard" target="_blank">Spotify Developer Dashboard</a><br>
                2. Click <strong>"Create app"</strong><br>
                3. Fill in:
                <ul style="margin-left: 20px; margin-top: 10px;">
                    <li><strong>App name:</strong> Spotify Copyright Checker</li>
                    <li><strong>Redirect URI:</strong> <span class="code">http://127.0.0.1:5000/callback</span></li>
                </ul>
                4. Click <strong>"Save"</strong>
            </div>
        </div>

        <div class="step">
            <div class="step-title">
                <span class="step-number">2</span>
                Get Your Credentials
            </div>
            <div class="step-content">
                1. On your app's page, click <strong>"Settings"</strong><br>
                2. Copy your <strong>Client ID</strong><br>
                3. Click <strong>"View client secret"</strong> and copy it
            </div>
        </div>

        <div class="step">
            <div class="step-title">
                <span class="step-number">3</span>
                Enter Your Credentials Below
            </div>
            <div class="step-content">
                <form method="POST" action="/setup">
                    <div class="form-group">
                        <label for="client_id">Client ID</label>
                        <input type="text" id="client_id" name="client_id" required 
                               placeholder="e.g., 6732f7efa12b49ffa356b88586e9671e">
                    </div>

                    <div class="form-group">
                        <label for="client_secret">Client Secret</label>
                        <input type="password" id="client_secret" name="client_secret" required 
                               placeholder="Enter your client secret">
                    </div>

                    <div class="warning-box">
                        ⚠️ <strong>Important:</strong> Your credentials will be stored locally in 
                        <span class="code">spotify_config.json</span>. Keep this file secure and 
                        don't share it publicly.
                    </div>

                    <button type="submit" class="btn">Save & Continue</button>
                </form>
            </div>
        </div>

        <div class="info-box">
            💡 <strong>Tip:</strong> Make sure to add <span class="code">http://127.0.0.1:5000/callback</span> 
            to your Spotify app's Redirect URIs in the dashboard!
        </div>
    </div>
</body>
</html>
'''

HOME_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Spotify Copyright Checker</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1DB954 0%, #191414 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            max-width: 500px;
            width: 100%;
            text-align: center;
        }
        h1 {
            color: #191414;
            margin-bottom: 10px;
            font-size: 2em;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
        }
        .spotify-btn {
            background: #1DB954;
            color: white;
            border: none;
            padding: 15px 40px;
            border-radius: 30px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            text-decoration: none;
            display: inline-block;
            margin: 10px;
        }
        .spotify-btn:hover {
            background: #1ed760;
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(29, 185, 84, 0.4);
        }
        .secondary-btn {
            background: #666;
        }
        .secondary-btn:hover {
            background: #777;
        }
        .features {
            text-align: left;
            margin-top: 30px;
            padding-top: 30px;
            border-top: 1px solid #eee;
        }
        .feature {
            margin: 15px 0;
            color: #333;
        }
        .feature::before {
            content: "✓";
            color: #1DB954;
            font-weight: bold;
            margin-right: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎵 Spotify Copyright Checker</h1>
        <p class="subtitle">Check copyright information for any Spotify content</p>
        
        <a href="/login" class="spotify-btn">Connect with Spotify</a>
        <a href="/setup" class="spotify-btn secondary-btn">⚙️ Settings</a>
        
        <div class="features">
            <div class="feature">Check albums, tracks, and playlists</div>
            <div class="feature">View your saved tracks</div>
            <div class="feature">Search and analyze any song</div>
            <div class="feature">100% free and secure</div>
        </div>
    </div>
</body>
</html>
'''

DASHBOARD_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Spotify Copyright Checker - Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #191414;
            color: white;
            padding: 20px;
        }
        .header {
            background: #1DB954;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header-buttons {
            display: flex;
            gap: 10px;
        }
        .logout-btn, .settings-btn {
            background: white;
            color: #1DB954;
            border: none;
            padding: 10px 20px;
            border-radius: 20px;
            cursor: pointer;
            font-weight: bold;
            text-decoration: none;
        }
        .search-box {
            background: #282828;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
        }
        input, select {
            width: 100%;
            padding: 15px;
            border: none;
            border-radius: 5px;
            margin-bottom: 15px;
            font-size: 16px;
        }
        .btn {
            background: #1DB954;
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 30px;
            font-size: 16px;
            cursor: pointer;
            font-weight: bold;
        }
        .btn:hover { background: #1ed760; }
        .btn-secondary {
            background: #535353;
        }
        .btn-secondary:hover { background: #636363; }
        .results {
            background: #282828;
            padding: 30px;
            border-radius: 10px;
            display: none;
        }
        .track {
            background: #333;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 15px;
        }
        .track-name { font-weight: bold; font-size: 18px; }
        .track-artist { color: #aaa; margin: 5px 0; }
        .copyright { 
            color: #1DB954; 
            font-size: 14px;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #444;
        }
        .license-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
        }
        .license-ok { background: #1e7e34; color: #fff; }
        .license-bad { background: #a71d2a; color: #fff; }
        .track { cursor: pointer; }
        .track:hover { background: #3a3a3a; }
        .loading {
            text-align: center;
            padding: 40px;
            display: none;
        }
        .playlist-list {
            max-height: 400px;
            overflow-y: auto;
            background: #333;
            border-radius: 5px;
            padding: 10px;
            margin-bottom: 15px;
            display: none;
        }
        .playlist-item {
            background: #444;
            padding: 15px;
            margin: 10px 0;
            border-radius: 5px;
            cursor: pointer;
            transition: background 0.3s;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .playlist-item:hover {
            background: #555;
        }
        .playlist-info {
            flex-grow: 1;
        }
        .playlist-name {
            font-weight: bold;
            font-size: 16px;
            margin-bottom: 5px;
        }
        .playlist-meta {
            color: #aaa;
            font-size: 14px;
        }
        .input-group {
            position: relative;
            margin-bottom: 15px;
        }
        #urlInput {
            display: block;
        }
        #playlistSelect {
            display: none;
        }
        /* Modal */
        .modal-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.6);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        .modal {
            background: #222;
            color: #fff;
            width: 90%;
            max-width: 800px;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }
        .modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; background: #1DB954; color: #191414; }
        .modal-body { padding: 20px; background: #2a2a2a; }
        .modal-close { background: transparent; border: none; font-size: 20px; cursor: pointer; color: #191414; }
        .details-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .detail-box { background: #333; padding: 12px; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎵 Copyright Checker</h1>
        <div class="header-buttons">
            <a href="/setup" class="settings-btn">⚙️ Settings</a>
            <a href="/logout"><button class="logout-btn">Logout</button></a>
        </div>
    </div>

    <div class="search-box">
        <h2>What do you want to check?</h2>
        <br>
        <select id="checkType" onchange="handleTypeChange()">
            <option value="url">Spotify URL (Album/Track/Playlist)</option>
            <option value="myplaylists">My Playlists</option>
            <option value="saved">My Saved Tracks</option>
            <option value="search">Search Tracks</option>
        </select>

        <div class="input-group">
            <input type="text" id="urlInput" placeholder="Paste Spotify URL or search query">
            <div id="playlistSelect" class="playlist-list"></div>
        </div>
        <div id="rangeInputs" style="display:none; gap: 10px;">
            <input type="number" id="rangeStart" placeholder="Start index" min="1" style="width: 49%;">
            <input type="number" id="rangeEnd" placeholder="End index" min="1" style="width: 49%;">
        </div>
        
        <button class="btn btn-secondary" id="loadPlaylistsBtn" onclick="loadMyPlaylists()" style="display: none; margin-bottom: 15px; width: 100%;">
            📋 Load My Playlists
        </button>

        <input type="number" id="limitValue" placeholder="Number of results (optional)" min="1" max="50" value="20">
        
        <button class="btn" onclick="checkCopyright()">Check Copyright</button>
    </div>

    <div class="loading" id="loading">
        <h2>⏳ Loading...</h2>
    </div>

    <div class="results" id="results">
        <h2 id="resultsTitle"></h2>
        <div id="trackList"></div>
    </div>

    <!-- Modal for track details -->
    <div id="modalOverlay" class="modal-overlay" onclick="closeModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal-header">
                <div id="modalTitle">Track details</div>
                <button class="modal-close" onclick="closeModal(event)">✕</button>
            </div>
            <div class="modal-body">
                <div id="modalContent">Loading…</div>
            </div>
        </div>
    </div>

    <script>
        let selectedPlaylistId = null;

        function handleTypeChange() {
            const type = document.getElementById('checkType').value;
            const urlInput = document.getElementById('urlInput');
            const playlistSelect = document.getElementById('playlistSelect');
            const loadBtn = document.getElementById('loadPlaylistsBtn');
            const limitValue = document.getElementById('limitValue');
            const rangeInputs = document.getElementById('rangeInputs');

            // Reset
            urlInput.style.display = 'none';
            playlistSelect.style.display = 'none';
            loadBtn.style.display = 'none';
            selectedPlaylistId = null;
            rangeInputs.style.display = 'none';

            if (type === 'url') {
                urlInput.style.display = 'block';
                urlInput.placeholder = 'Paste Spotify URL';
                limitValue.style.display = 'none';
            } else if (type === 'myplaylists') {
                loadBtn.style.display = 'block';
                limitValue.style.display = 'none';
                rangeInputs.style.display = 'grid';
            } else if (type === 'saved') {
                limitValue.style.display = 'block';
                urlInput.style.display = 'none';
            } else if (type === 'search') {
                urlInput.style.display = 'block';
                urlInput.placeholder = 'Enter search query';
                limitValue.style.display = 'block';
            }
        }

        function loadMyPlaylists() {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('results').style.display = 'none';

            fetch('/api/my-playlists')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('loading').style.display = 'none';

                    if (data.error) {
                        alert('Error loading playlists: ' + data.error);
                        return;
                    }

                    const playlistSelect = document.getElementById('playlistSelect');
                    playlistSelect.style.display = 'block';
                    
                    let html = '<h3 style="padding: 10px; color: #1DB954;">Select a Playlist:</h3>';
                    data.playlists.forEach(playlist => {
                        html += `
                            <div class="playlist-item" onclick="selectPlaylist('${playlist.id}', '${playlist.name.replace(/'/g, "\\'")}')">
                                <div class="playlist-info">
                                    <div class="playlist-name">${playlist.name}</div>
                                    <div class="playlist-meta">${playlist.tracks} tracks • ${playlist.owner}</div>
                                </div>
                                <div>▶</div>
                            </div>
                        `;
                    });
                    playlistSelect.innerHTML = html;
                })
                .catch(error => {
                    document.getElementById('loading').style.display = 'none';
                    alert('Error: ' + error);
                });
        }

        function selectPlaylist(playlistId, playlistName) {
            selectedPlaylistId = playlistId;
            
            // Highlight selected playlist
            const items = document.querySelectorAll('.playlist-item');
            items.forEach(item => item.style.background = '#444');
            event.currentTarget.style.background = '#1DB954';
            
            console.log('Selected playlist:', playlistName, playlistId);
        }

        function checkCopyright() {
            const type = document.getElementById('checkType').value;
            const input = document.getElementById('urlInput').value;
            const limit = document.getElementById('limitValue').value || 20;

            document.getElementById('loading').style.display = 'block';
            document.getElementById('results').style.display = 'none';

            let url = '';
            if (type === 'url') {
                url = `/api/check-url?url=${encodeURIComponent(input)}`;
            } else if (type === 'myplaylists') {
                if (!selectedPlaylistId) {
                    document.getElementById('loading').style.display = 'none';
                    alert('Please select a playlist first!');
                    return;
                }
                const s = document.getElementById('rangeStart').value;
                const e = document.getElementById('rangeEnd').value;
                const range = (s && e) ? `&start=${s}&end=${e}` : '';
                url = `/api/check-playlist?playlist_id=${selectedPlaylistId}${range}`;
            } else if (type === 'saved') {
                url = `/api/saved-tracks?limit=${limit}`;
            } else if (type === 'search') {
                url = `/api/search?query=${encodeURIComponent(input)}&limit=${limit}`;
            }

            fetch(url)
                .then(response => response.json())
                .then(data => {
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('results').style.display = 'block';
                    
                    if (data.error) {
                        document.getElementById('resultsTitle').textContent = 'Error: ' + data.error;
                        document.getElementById('trackList').innerHTML = '';
                        return;
                    }

                    document.getElementById('resultsTitle').textContent = 
                        data.title || `Found ${data.tracks.length} tracks`;

                    let html = '';
                    data.tracks.forEach(track => {
                        html += `
                            <div class="track" onclick="openTrackDetails('${track.id}')">
                                <div class="track-name">${track.name}</div>
                                <div class="track-artist">${track.artist}</div>
                                <div style="display:flex; gap:10px; align-items:center; margin-top:8px; flex-wrap: wrap;">
                                    <span class="license-badge ${track.license?.is_free ? 'license-ok' : 'license-bad'}">
                                        ${track.license?.is_free ? '✓ Copyright-free (heuristic)' : '✕ Likely copyrighted'}
                                    </span>
                                    <span style="font-size:12px; color:#aaa;">Conf: ${track.license?.confidence ?? 0}</span>
                                </div>
                                <div class="copyright">
                                    ${track.copyrights.length > 0 
                                        ? track.copyrights.map(c => `${c.type}: ${c.text}`).join('<br>')
                                        : '⚠️ No copyright information found'}
                                </div>
                            </div>
                        `;
                    });
                    document.getElementById('trackList').innerHTML = html;
                })
                .catch(error => {
                    document.getElementById('loading').style.display = 'none';
                    alert('Error: ' + error);
                });
        }

        // Initialize on load
        handleTypeChange();

        function openTrackDetails(trackId) {
            if (!trackId) return;
            const overlay = document.getElementById('modalOverlay');
            const content = document.getElementById('modalContent');
            const title = document.getElementById('modalTitle');
            overlay.style.display = 'flex';
            content.innerHTML = 'Loading…';
            fetch(`/api/track-details?track_id=${trackId}`)
                .then(r => r.json())
                .then(data => {
                    if (data.error) { content.innerHTML = 'Error: ' + data.error; return; }
                    title.textContent = `${data.track.name} — ${data.track.artist}`;
                    const l = data.license;
                    const badge = `<span class="license-badge ${l.is_free ? 'license-ok' : 'license-bad'}">${l.is_free ? '✓ Copyright-free (heuristic)' : '✕ Likely copyrighted'}</span>`;
                    let featuresHtml = '';
                    if (data.audio_features && data.audio_features._has_data) {
                        featuresHtml = `
                            <div class="detail-box">
                                <strong>Audio Features</strong><br>
                                Tempo: ${data.audio_features.tempo} BPM<br>
                                Key: ${data.audio_features.key} • Mode: ${data.audio_features.mode}<br>
                                Danceability: ${data.audio_features.danceability}<br>
                                Energy: ${data.audio_features.energy}
                            </div>`;
                    }
                    content.innerHTML = `
                        <div style="margin-bottom: 10px; display:flex; gap:10px; align-items:center;">${badge}<span style="font-size:12px; color:#aaa;">Conf: ${l.confidence}</span></div>
                        <div class="details-grid">
                            <div class="detail-box">
                                <strong>Album</strong><br>${data.album.name} (${data.album.release_date})<br>Label: ${data.album.label || '—'}
                            </div>
                            <div class="detail-box">
                                <strong>Popularity</strong><br>${data.track.popularity}/100<br><strong>Explicit:</strong> ${data.track.explicit ? 'Yes' : 'No'}
                            </div>
                            ${featuresHtml}
                            <div class="detail-box">
                                <strong>Signals</strong><br>
                                Positive: ${(l.signals.positive || []).join(', ') || 'none'}<br>
                                Negative: ${(l.signals.negative || []).join(', ') || 'none'}
                            </div>
                            <div class="detail-box" style="grid-column: 1 / -1;">
                                <strong>Copyrights</strong><br>
                                ${(data.album.copyrights || []).map(c => `${c.type}: ${c.text}`).join('<br>') || 'None'}
                            </div>
                        </div>
                    `;
                })
                .catch(err => { content.innerHTML = 'Error: ' + err; });
        }

        function closeModal(e) {
            document.getElementById('modalOverlay').style.display = 'none';
        }
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    if 'access_token' in session:
        return redirect('/dashboard')
    return render_template_string(HOME_PAGE)

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if request.method == 'POST':
        client_id = request.form.get('client_id', '').strip()
        client_secret = request.form.get('client_secret', '').strip()
        
        if not client_id or not client_secret:
            return render_template_string(SETUP_PAGE, error="Both Client ID and Client Secret are required!")
        
        save_config(client_id, client_secret)
        return redirect('/?setup=success')
    
    return render_template_string(SETUP_PAGE)

@app.route('/login')
def login():
    client_id, client_secret = get_credentials()
    
    if not client_id or not client_secret:
        return redirect('/setup')
    
    auth_url = 'https://accounts.spotify.com/authorize?' + urlencode({
        'client_id': client_id,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPES
    })
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    client_id, client_secret = get_credentials()
    
    if not client_id or not client_secret:
        return redirect('/setup')
    
    token_url = 'https://accounts.spotify.com/api/token'
    token_data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'client_id': client_id,
        'client_secret': client_secret
    }
    
    response = requests.post(token_url, data=token_data)
    if response.status_code == 200:
        token_info = response.json()
        session['access_token'] = token_info['access_token']
        return redirect('/dashboard')
    else:
        return f'Error: {response.text}'

@app.route('/dashboard')
def dashboard():
    if 'access_token' not in session:
        return redirect('/')
    return render_template_string(DASHBOARD_PAGE)

@app.route('/logout')
def logout():
    session.pop('access_token', None)
    return redirect('/')

def make_spotify_request(endpoint, params=None):
    if 'access_token' not in session:
        return None
    
    headers = {'Authorization': f"Bearer {session['access_token']}"}
    url = f"https://api.spotify.com/v1/{endpoint}"
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        return response.json()
    return None

@app.route('/api/check-url')
def check_url():
    url = request.args.get('url')
    pattern = r'https://open\.spotify\.com/(album|track|playlist)/([a-zA-Z0-9]+)'
    match = re.search(pattern, url)
    
    if not match:
        return jsonify({'error': 'Invalid Spotify URL'})
    
    content_type = match.group(1)
    content_id = match.group(2)
    
    tracks = []
    title = ''
    
    if content_type == 'album':
        album = make_spotify_request(f'albums/{content_id}')
        if album:
            title = f"Album: {album['name']} by {album['artists'][0]['name']}"
            for track in album['tracks']['items']:
                license_check = classify_license_from_metadata(
                    track.get('name'),
                    ', '.join([a['name'] for a in track.get('artists', [])]),
                    album.get('label'),
                    ' '.join([c.get('text', '') for c in album.get('copyrights', [])])
                )
                tracks.append({
                    'id': track['id'],
                    'name': track['name'],
                    'artist': track['artists'][0]['name'],
                    'license': license_check,
                    'copyrights': album.get('copyrights', [])
                })
    
    elif content_type == 'track':
        track = make_spotify_request(f'tracks/{content_id}')
        if track:
            album = make_spotify_request(f"albums/{track['album']['id']}")
            license_check = classify_license_from_metadata(
                track.get('name'),
                ', '.join([a['name'] for a in track.get('artists', [])]),
                (album or {}).get('label'),
                ' '.join([c.get('text', '') for c in (album or {}).get('copyrights', [])])
            )
            tracks.append({
                'id': track['id'],
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'license': license_check,
                'copyrights': album.get('copyrights', []) if album else []
            })
    
    elif content_type == 'playlist':
        playlist = make_spotify_request(f'playlists/{content_id}')
        if playlist:
            title = f"Playlist: {playlist['name']}"
            playlist_tracks = make_spotify_request(f'playlists/{content_id}/tracks')
            if playlist_tracks:
                for item in playlist_tracks['items'][:20]:
                    track = item.get('track')
                    if track:
                        album = make_spotify_request(f"albums/{track['album']['id']}")
                        license_check = classify_license_from_metadata(
                            track.get('name'),
                            ', '.join([a['name'] for a in track.get('artists', [])]),
                            (album or {}).get('label'),
                            ' '.join([c.get('text', '') for c in (album or {}).get('copyrights', [])])
                        )
                        tracks.append({
                            'id': track['id'],
                            'name': track['name'],
                            'artist': track['artists'][0]['name'],
                            'license': license_check,
                            'copyrights': album.get('copyrights', []) if album else []
                        })
    
    return jsonify({'tracks': tracks, 'title': title})

@app.route('/api/saved-tracks')
def saved_tracks():
    limit = int(request.args.get('limit', 20))
    
    results = make_spotify_request('me/tracks', params={'limit': limit})
    tracks = []
    
    if results:
        for item in results['items']:
            track = item['track']
            album = make_spotify_request(f"albums/{track['album']['id']}")
            license_check = classify_license_from_metadata(
                track.get('name'),
                ', '.join([a['name'] for a in track.get('artists', [])]),
                (album or {}).get('label'),
                ' '.join([c.get('text', '') for c in (album or {}).get('copyrights', [])])
            )
            tracks.append({
                'id': track['id'],
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'license': license_check,
                'copyrights': album.get('copyrights', []) if album else []
            })
    
    return jsonify({'tracks': tracks, 'title': 'Your Saved Tracks'})

@app.route('/api/search')
def search():
    query = request.args.get('query')
    limit = int(request.args.get('limit', 20))
    
    results = make_spotify_request('search', params={
        'q': query,
        'type': 'track',
        'limit': limit
    })
    
    tracks = []
    if results and 'tracks' in results:
        for track in results['tracks']['items']:
            album = make_spotify_request(f"albums/{track['album']['id']}")
            license_check = classify_license_from_metadata(
                track.get('name'),
                ', '.join([a['name'] for a in track.get('artists', [])]),
                (album or {}).get('label'),
                ' '.join([c.get('text', '') for c in (album or {}).get('copyrights', [])])
            )
            tracks.append({
                'id': track['id'],
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'license': license_check,
                'copyrights': album.get('copyrights', []) if album else []
            })
    
    return jsonify({'tracks': tracks, 'title': f"Search results for '{query}'"})

@app.route('/api/my-playlists')
def my_playlists():
    """Get the current user's playlists"""
    playlists = []
    offset = 0
    limit = 50
    
    while True:
        results = make_spotify_request('me/playlists', params={'offset': offset, 'limit': limit})
        if not results or not results.get('items'):
            break
        
        for playlist in results['items']:
            playlists.append({
                'id': playlist['id'],
                'name': playlist['name'],
                'tracks': playlist['tracks']['total'],
                'owner': playlist['owner']['display_name']
            })
        
        if not results.get('next'):
            break
        offset += limit
    
    return jsonify({'playlists': playlists})

@app.route('/api/check-playlist')
def check_playlist():
    """Check copyright info for a specific playlist"""
    playlist_id = request.args.get('playlist_id')
    
    if not playlist_id:
        return jsonify({'error': 'No playlist ID provided'})
    
    # Get playlist info
    playlist = make_spotify_request(f'playlists/{playlist_id}')
    if not playlist:
        return jsonify({'error': 'Could not fetch playlist'})
    
    title = f"Playlist: {playlist['name']} by {playlist['owner']['display_name']}"
    
    # Get playlist tracks
    tracks = []
    offset = 0
    limit = 100
    # Optional range selection
    try:
        start = int(request.args.get('start') or 1)
        end = int(request.args.get('end') or 0)
    except ValueError:
        start, end = 1, 0
    if start < 1:
        start = 1
    idx_global = 0
    
    while True:
        playlist_tracks = make_spotify_request(f'playlists/{playlist_id}/tracks', 
                                               params={'offset': offset, 'limit': limit})
        if not playlist_tracks or not playlist_tracks.get('items'):
            break
        
        for item in playlist_tracks['items']:
            track = item.get('track')
            if track:
                idx_global += 1
                if end and (idx_global < start or idx_global > end):
                    continue
                album = make_spotify_request(f"albums/{track['album']['id']}")
                license_check = classify_license_from_metadata(
                    track.get('name'),
                    ', '.join([a['name'] for a in track.get('artists', [])]),
                    (album or {}).get('label'),
                    ' '.join([c.get('text', '') for c in (album or {}).get('copyrights', [])])
                )
                tracks.append({
                    'id': track['id'],
                    'name': track['name'],
                    'artist': track['artists'][0]['name'],
                    'license': license_check,
                    'copyrights': album.get('copyrights', []) if album else []
                })
        
        if not playlist_tracks.get('next'):
            break
        offset += limit
    
    # Append range info to title if applied
    if start != 1 or end:
        rng = f" (range: {start}-{end if end else idx_global})"
        title = title + rng
    return jsonify({'tracks': tracks, 'title': title})

@app.route('/api/track-details')
def track_details():
    """Return detailed information for a track, including album, features, and license heuristic."""
    track_id = request.args.get('track_id')
    if not track_id:
        return jsonify({'error': 'No track_id provided'})

    track = make_spotify_request(f'tracks/{track_id}')
    if not track:
        return jsonify({'error': 'Could not fetch track'})

    album = make_spotify_request(f"albums/{track['album']['id']}") or {}
    artists = track.get('artists', [])
    features = make_spotify_request('audio-features/' + track_id) or {}

    license_check = classify_license_from_metadata(
        track.get('name'),
        ', '.join([a['name'] for a in artists]),
        album.get('label'),
        ' '.join([c.get('text', '') for c in album.get('copyrights', [])])
    )

    # Determine if audio features actually contain data
    af = {
        'tempo': features.get('tempo'),
        'key': features.get('key'),
        'mode': features.get('mode'),
        'danceability': features.get('danceability'),
        'energy': features.get('energy')
    }
    af['_has_data'] = any(v is not None for v in af.values() if not isinstance(v, bool))

    return jsonify({
        'track': {
            'id': track.get('id'),
            'name': track.get('name'),
            'artist': artists[0]['name'] if artists else '',
            'explicit': track.get('explicit'),
            'popularity': track.get('popularity')
        },
        'album': {
            'id': album.get('id'),
            'name': album.get('name'),
            'label': album.get('label'),
            'release_date': album.get('release_date'),
            'copyrights': album.get('copyrights', [])
        },
        'audio_features': af,
        'license': license_check
    })

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Spotify Copyright Checker Web App")
    print("=" * 60)
    print("\n✨ NEW: Setup page included!")
    print("   No need to edit the script - configure through the web interface!")
    print("\n📝 Setup Instructions:")
    print("1. Open browser to: http://127.0.0.1:5000")
    print("2. Click 'Settings' button")
    print("3. Follow the setup wizard")
    print("\n⚙️ Make sure to add this redirect URI to Spotify Dashboard:")
    print("   http://127.0.0.1:5000/callback")
    print("=" * 60)
    print()
    
    app.run(debug=True, host='127.0.0.1', port=5000)