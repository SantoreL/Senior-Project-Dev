from flask import Flask, request, redirect, session, render_template, render_template_string, jsonify, url_for
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


@app.route('/')
def home():
    if 'access_token' in session:
        return redirect('/dashboard')
    return render_template('home.html')

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if request.method == 'POST':
        client_id = request.form.get('client_id', '').strip()
        client_secret = request.form.get('client_secret', '').strip()
        
        if not client_id or not client_secret:
            return render_template('setup.html', error="Both Client ID and Client Secret are required!") 
        
        save_config(client_id, client_secret)
        return redirect('/?setup=success')
    
    return render_template('setup.html')

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
    return render_template('dashboard.html')

@app.route('/logout')
def logout():
    session.pop('access_token', None)
    return redirect('/')


@app.route('/bookmarked')
def bookmarked():
    if 'access_token' not in session: 
        return redirect('/')
    return render_template('bookmarked.html')

def make_spotify_request(endpoint, method='GET',params=None): # if no method default is get 
    if 'access_token' not in session:
        return None
    
    headers = {'Authorization': f"Bearer {session['access_token']}"}
    url = f"https://api.spotify.com/v1/{endpoint}"
    
    if method == 'GET':
        response = requests.get(url, headers=headers, params=params)
    elif method == 'POST':
        response = requests.post(url, headers=headers, json=json)
    # response = requests.get(url, headers=headers, params=params)
    
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



# create playlist 
# add to playlist 
@app.route('/api/add-playlist-items', methods=['POST'])
def add_track():
    
    # POST add to their playlist, used to save from front end 
    track_id = request.args.get('track_id')
    playlist_id = request.json.get('playlist_id')
    if not playlist_id:
        return jsonify({'error': 'No track_id provided'})
     
    uri = f"spotify:track:{track_id}"

    result = make_spotify_request(
        f'playlists/{playlist_id}/tracks',
        method='POST',
        json={'uris': [uri]}
    )

    
    return jsonify({'playlist': result})
    
# delete from 
@app.route('/api/delete-playlist-items')
def remove_track():
    playlist_id = request.args.get('playlist_id')
    if not playlist_id:
        return jsonify({'error': 'No playlist_id provided'})

    
    # remove from their playlist 
    playlist = make_spotify_request(f'/playlists/{playlist_id}/tracks')



if __name__ == '__main__':
    print("=" * 60)
    print("Spotify Copyright Checker Web App")
    print("=" * 60)
    print("\n NEW: Setup page included!")
    print("   No need to edit the script - configure through the web interface!")
    print("\n📝Setup Instructions:")
    print("1. Open browser to: http://127.0.0.1:5000")
    print("2. Click 'Settings' button")
    print("3. Follow the setup wizard")
    print("\n Make sure to add this redirect URI to Spotify Dashboard:")
    print("   http://127.0.0.1:5000/callback")
    print("=" * 60)
    print()
    
    app.run(debug=True, host='127.0.0.1', port=5000)