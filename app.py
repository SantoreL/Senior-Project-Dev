from flask import Flask, request, redirect, session, render_template, render_template_string, jsonify, url_for
import requests
from urllib.parse import urlencode
import secrets
import os
import json
import re

app = Flask(__name__, static_folder='static', static_url_path='/static')
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
SCOPES = 'user-library-read playlist-read-private playlist-read-collaborative user-read-private user-read-email playlist-modify-public playlist-modify-private'
# ------------------------------
# Heuristic license classifier
# ------------------------------
# Positive keywords - push heuristic in positive direction (no individual weights needed)
POSITIVE_LICENSE_KEYWORDS = [
    'public domain', 'cc0', 'cc 0', 'no copyright', 'copyright free', 'copyright-free',
    'creative commons', 'free for commercial', 'free for monetization', 'youtube safe',
    'royalty free', 'royalty-free', 'free to use', 'free use', 'license free'
]

# Negative keywords - push heuristic in negative direction (no individual weights needed)
NEGATIVE_LICENSE_KEYWORDS = [
    'all rights reserved', 'under exclusive license', 'exclusive license', 'unauthorized',
    'broadcast prohibited', 'for promotional use only', 'not for resale', 'licensed to',
    'universal music', 'sony music entertainment', 'umg', 'warner', 'wmg', 'sony',
    'atlantic records', 'columbia records', 'rca records', 'def jam', 'republic records',
    'interscope', 'ltc', 'sme'
]

# Labels/brands that usually publish copyright-free music with confidence weights
POSITIVE_LABELS = {
    'ncs': 0.25,
    'nocopyrightsounds': 0.25,
    'chillhop records': 0.20,
    'chillhop music': 0.20,
    'audio library': 0.18,
    'epidemic sound free': 0.18,
    'streambeats': 0.18,
    'infraction': 0.18,

}

# Bad labels that indicate copyrighted content with confidence weights
BAD_LABELS = {
    # Very strong indicators
    '©': 0.20,
    '℗': 0.20,
    '(c)': 0.18,
    '(p)': 0.18,
    '(c) ': 0.18,
    '(p) ': 0.18,
    
    # Strong indicators
    'music publishing': 0.15,
    'rights reserved': 0.15,
    'copyrighted': 0.15,
    'copyright': 0.15,
    'copyrighted': 0.15,
    'rights mangement': 0.15,
    'warner': 0.12,
    'Warner': 0.12,
    'sony': 0.12,
    'Sony': 0.12,
    
    # Medium indicators
    'records': 0.10,
    'llc': 0.10,
    'production': 0.10,

}

def _normalize_text(value):
    if not value:
        return ''
    if isinstance(value, (list, tuple)):
        return ' '.join(_normalize_text(v) for v in value)
    return str(value).lower()

def classify_license_from_metadata(*texts, release_date=None, label=None):
    """Keyword-based check with labels as definitive indicators. Returns dict with is_free, confidence, signals, reason, status."""
    blob = _normalize_text(list(texts))
    
    # Find positive keywords (simple list matching - no weights)
    positives = [kw for kw in POSITIVE_LICENSE_KEYWORDS if kw in blob]
    
    # Find negative keywords (simple list matching - no weights)
    negatives = [kw for kw in NEGATIVE_LICENSE_KEYWORDS if kw in blob]

    # Check for bad labels in the label field and copyright symbols in the blob
    # Bad labels are definitive indicators with weights
    bad_label_hits = {}
    if label:
        label_normalized = _normalize_text(label)
        # Check all bad labels in the label field
        for bad_lbl, weight in BAD_LABELS.items():
            if bad_lbl in label_normalized and bad_lbl not in bad_label_hits:
                bad_label_hits[bad_lbl] = weight
    # Also check for copyright symbols in the blob (they can appear in copyright text)
    for bad_lbl in ['©', '℗', '(c)', '(p)', '(c) ', '(p) ']:
        if bad_lbl in blob and bad_lbl not in bad_label_hits:
            bad_label_hits[bad_lbl] = BAD_LABELS.get(bad_lbl, 0.15)
    bad_label_list = list(bad_label_hits.keys())
    bad_label_score = sum(bad_label_hits.values())

    # Check for positive labels - these are DEFINITIVE indicators with weights
    positive_label_hits = {}
    for lbl, weight in POSITIVE_LABELS.items():
        if lbl in blob:
            positive_label_hits[lbl] = weight
    positive_label_list = list(positive_label_hits.keys())
    positive_label_score = sum(positive_label_hits.values())
    positive_label_hit = len(positive_label_list) > 0

    # Check if release date is before 1923 (public domain in US)
    is_public_domain = False
    if release_date:
        try:
            # Extract year from release_date (format can be YYYY, YYYY-MM-DD, etc.)
            year_str = str(release_date).split('-')[0]
            year = int(year_str)
            if year < 1923:
                is_public_domain = True
        except (ValueError, AttributeError):
            pass

    # Keywords push the score in a direction (simple count-based)
    # Labels are definitive and override keyword-based scoring
    keyword_score = len(positives) - len(negatives)
    
    # If public domain, override to free
    if is_public_domain:
        is_free = True
    elif positive_label_hit:
        # Positive labels are definitive - they mean free
        is_free = True
    elif bad_label_score > 0.15:
        # Strong bad label indicators are definitive - they mean copyrighted
        is_free = False
    else:
        # Use keyword score to determine direction
        is_free = keyword_score > 0

    # Confidence calculation:
    # - Labels are DEFINITIVE indicators (high confidence)
    # - Keywords push confidence but don't give definitive answers
    # - Public domain gets highest confidence
    if is_public_domain:
        confidence = 0.95
    elif positive_label_hit:
        # Positive labels are definitive - high confidence
        confidence = 0.75 + min(0.20, positive_label_score)
        confidence = min(0.95, confidence)
    elif bad_label_score > 0.15:
        # Strong bad label indicators are definitive - high confidence in copyrighted
        confidence = 0.70 + min(0.20, bad_label_score)
        confidence = min(0.90, confidence)
    elif len(positives) == 0 and len(negatives) == 0 and len(bad_label_list) == 0:
        # No signals at all
        confidence = 0.4
    else:
        # Keywords push confidence but aren't definitive
        # Base confidence starts at 0.5
        base = 0.50
        
        # Keywords push in their direction (but not too strongly)
        if keyword_score > 0:
            base += min(0.15, keyword_score * 0.05)  # Max +0.15 for many positive keywords
        elif keyword_score < 0:
            base -= min(0.15, abs(keyword_score) * 0.05)  # Max -0.15 for many negative keywords
        
        # Bad labels (weak ones) also push confidence down
        if bad_label_score > 0:
            base -= min(0.10, bad_label_score)
        
        confidence = max(0.35, min(0.70, base))  # Cap at 0.70 for keyword-only results

    # Determine status: if confidence is too low, mark as "unsure"
    # Threshold: confidence < 0.45
    status = 'unsure' if confidence < 0.45 else ('free' if is_free else 'copyrighted')

    # Build reason string
    reason_parts = []
    if is_public_domain:
        reason_parts.append(f"Public domain (released before 1923: {release_date})")
    if positives:
        reason_parts.append(f"positive keywords: {', '.join(positives)}")
    if positive_label_list:
        reason_parts.append(f"positive labels: {', '.join(positive_label_list)}")
    if negatives:
        reason_parts.append(f"negative keywords: {', '.join(negatives)}")
    if bad_label_list:
        reason_parts.append(f"bad label indicators: {', '.join(bad_label_list)}")
    
    reason = '; '.join(reason_parts) if reason_parts else 'No clear signals detected.'

    return {
        'is_free': bool(is_free),
        'confidence': round(confidence, 2),
        'status': status,
        'signals': {
            'positive': positives + positive_label_list + (['public domain'] if is_public_domain else []),
            'negative': negatives + bad_label_list
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

    if response.status_code != 200:
        return f"Error: {response.text}"

    
    token_info = response.json()
    session['access_token'] = token_info['access_token']

    
    user_data = make_spotify_request("me")
    if user_data:
        session["user_id"] = user_data["id"]

    return redirect('/dashboard')


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

def make_spotify_request(endpoint, method='GET',params=None, json=None): # if no method default is get, changed to accept post
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
                    'release_date': album.get('release_date'), # add release date so we can sort 
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



# used AI to help debug this part. 
@app.route('/api/create-playlist', methods=['POST'])
def create_playlist():
    if 'access_token' not in session:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.json
    name = data.get("name")
    description = data.get("description", "")
    public = data.get("public", False)

    url = "https://api.spotify.com/v1/me/playlists"
    headers = {
        "Authorization": f"Bearer {session['access_token']}",
        "Content-Type": "application/json"
    }

    
    payload = {
        "name": name,
        "description": description,
        "public": public
    }

    response = requests.post(url, headers=headers, json=payload)

    
    if response.status_code not in (200, 201):
        return jsonify({"error": response.text}), response.status_code

    return jsonify(response.json())




@app.route('/api/add-playlist-items', methods=['POST'])
def add_track():
    data = request.json  # Get the JSON body
    track_id = data.get('track_id')  
    playlist_id = data.get('playlist_id')  
    
    if not playlist_id:
        return jsonify({'error': 'No playlist_id provided'})
    if not track_id:
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
    data = request.json  # Get the JSON body
    track_id = data.get('track_id') 
    playlist_id = data.get('playlist_id') 
    
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
    print("\n Setup Instructions:")
    print("1. Open browser to: http://127.0.0.1:5000")
    print("2. Click 'Settings' button")
    print("3. Follow the setup wizard")
    print("\n Make sure to add this redirect URI to Spotify Dashboard:")
    print("   http://127.0.0.1:5000/callback")
    print("=" * 60)
    print()
    
    app.run(debug=True, host='127.0.0.1', port=5000)