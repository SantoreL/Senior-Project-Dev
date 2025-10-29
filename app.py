from flask import Flask, request, redirect, session, render_template_string, jsonify, url_for
import requests
from urllib.parse import urlencode
import secrets
import os
import json

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Config file to store credentials
CONFIG_FILE = 'spotify_config.json'

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

    <script>
        let selectedPlaylistId = null;

        function handleTypeChange() {
            const type = document.getElementById('checkType').value;
            const urlInput = document.getElementById('urlInput');
            const playlistSelect = document.getElementById('playlistSelect');
            const loadBtn = document.getElementById('loadPlaylistsBtn');
            const limitValue = document.getElementById('limitValue');

            // Reset
            urlInput.style.display = 'none';
            playlistSelect.style.display = 'none';
            loadBtn.style.display = 'none';
            selectedPlaylistId = null;

            if (type === 'url') {
                urlInput.style.display = 'block';
                urlInput.placeholder = 'Paste Spotify URL';
                limitValue.style.display = 'none';
            } else if (type === 'myplaylists') {
                loadBtn.style.display = 'block';
                limitValue.style.display = 'none';
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
                url = `/api/check-playlist?playlist_id=${selectedPlaylistId}`;
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
                            <div class="track">
                                <div class="track-name">${track.name}</div>
                                <div class="track-artist">${track.artist}</div>
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
    import re
    
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
                tracks.append({
                    'name': track['name'],
                    'artist': track['artists'][0]['name'],
                    'copyrights': album.get('copyrights', [])
                })
    
    elif content_type == 'track':
        track = make_spotify_request(f'tracks/{content_id}')
        if track:
            album = make_spotify_request(f"albums/{track['album']['id']}")
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
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
                        tracks.append({
                            'name': track['name'],
                            'artist': track['artists'][0]['name'],
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
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
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
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
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
    
    while True:
        playlist_tracks = make_spotify_request(f'playlists/{playlist_id}/tracks', 
                                               params={'offset': offset, 'limit': limit})
        if not playlist_tracks or not playlist_tracks.get('items'):
            break
        
        for item in playlist_tracks['items']:
            track = item.get('track')
            if track:
                album = make_spotify_request(f"albums/{track['album']['id']}")
                tracks.append({
                    'name': track['name'],
                    'artist': track['artists'][0]['name'],
                    'copyrights': album.get('copyrights', []) if album else []
                })
        
        if not playlist_tracks.get('next'):
            break
        offset += limit
    
    return jsonify({'tracks': tracks, 'title': title})

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