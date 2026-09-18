from flask import Flask, render_template, request, send_file, jsonify, url_for, session, redirect
import requests
import io
import os
import secrets
import hashlib
import base64
from functools import wraps
from urllib.parse import urlencode

app = Flask(__name__)
app.secret_key = "super-secret-key-for-session"

# --- CONFIGURATION ---
# App Key from Pollinations Dashboard (pk_ - public, safe to expose)
APP_KEY = "pk_I7Juq9TCkV9jG1wL"
APP_REDIRECT_URI = "https://personamorph-ai-production.up.railway.app/callback"
POLLINATIONS_AUTHORIZE_URL = "https://enter.pollinations.ai/authorize"
POLLINATIONS_TOKEN_URL = "https://enter.pollinations.ai/api/oauth/token"
EDIT_API_URL = "https://gen.pollinations.ai/v1/images/edits"
DEFAULT_MODEL = "community/sharktide/inferenceport-ai-lightning-image-turbo"

def generate_code_verifier():
    """Generate a PKCE code verifier (43-128 characters, base64url-encoded random bytes)."""
    return secrets.token_urlsafe(32)

def generate_code_challenge(verifier):
    """Generate S256 code challenge from verifier."""
    sha256_hash = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(sha256_hash).rstrip(b'=').decode('ascii')

@app.route('/')
def index():
    # Show connected state based on whether we have a token in session
    has_token = 'access_token' in session
    return render_template('index.html', logged_in=has_token)

@app.route('/connect')
def connect():
    """Initiate OAuth 2.0 Authorization Code flow with PKCE."""
    # Generate PKCE code_verifier and challenge
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(32)
    
    # Store in session for callback verification
    session['code_verifier'] = code_verifier
    session['oauth_state'] = state
    session['redirect_after_auth'] = request.args.get('next', url_for('index'))
    
    # Build the authorization URL with PKCE S256
    auth_params = {
        'response_type': 'code',
        'client_id': APP_KEY,
        'redirect_uri': APP_REDIRECT_URI,
        'scope': 'usage',
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256'
    }
    
    auth_url = f"{POLLINATIONS_AUTHORIZE_URL}?{urlencode(auth_params)}"
    return redirect(auth_url)

@app.route('/callback')
def callback():
    """Handle OAuth callback: exchange authorization code for access token."""
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    # Verify state to prevent CSRF
    if not state or state != session.get('oauth_state'):
        return jsonify({"error": "Invalid state parameter"}), 400
    
    if error:
        return jsonify({"error": f"OAuth error: {error}"}), 400
    
    if not code:
        return jsonify({"error": "No authorization code received"}), 400
    
    # Get the code_verifier from session
    code_verifier = session.get('code_verifier')
    if not code_verifier:
        return jsonify({"error": "PKCE code_verifier missing"}), 400
    
    # Exchange code for access token with PKCE
    try:
        token_res = requests.post(
            POLLINATIONS_TOKEN_URL,
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': APP_REDIRECT_URI,
                'client_id': APP_KEY,
                'code_verifier': code_verifier,
            },
            headers={'Accept': 'application/json'},
            timeout=30
        )
        
        if token_res.status_code != 200:
            return jsonify({
                "error": f"Token exchange failed: {token_res.status_code}",
                "details": token_res.text
            }), 400
        
        token_data = token_res.json()
        # Handle different response formats
        access_token = (
            token_data.get('access_token') or 
            token_data.get('token') or 
            token_data.get('id_token')
        )
        
        if not access_token:
            return jsonify({"error": "No access token in response", "response": token_data}), 400
        
        # Store the temporary token (expires in session)
        session['access_token'] = access_token
        session.pop('code_verifier', None)
        session.pop('oauth_state', None)
        
        # Redirect to the main page
        return redirect(session.get('redirect_after_auth', url_for('index')))
        
    except Exception as e:
        return jsonify({"error": f"Connection error: {str(e)}"}), 500

@app.route('/generate', methods=['POST'])
def generate():
    if 'access_token' not in session:
        return jsonify({"error": "Please connect your wallet first"}), 401
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    
    prompt = request.form.get('prompt', 'Cyberpunk transformation')
    model = request.form.get('model', DEFAULT_MODEL)
    image_file = request.files['image']
    access_token = session['access_token']
    
    try:
        files = {"image": (image_file.filename, image_file.read(), image_file.content_type)}
        data = {"prompt": prompt, "model": model}
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = requests.post(EDIT_API_URL, headers=headers, data=data, files=files, timeout=120)
        
        if response.status_code == 200:
            if response.headers.get('Content-Type') == 'application/json':
                import base64
                res_json = response.json()
                if "data" in res_json and "b64_json" in res_json["data"][0]:
                    img_data = base64.b64decode(res_json["data"][0]["b64_json"])
                    return send_file(io.BytesIO(img_data), mimetype='image/jpeg')
                return jsonify({"error": "Invalid API response format"}), 500
            
            return send_file(io.BytesIO(response.content), mimetype='image/jpeg')
        else:
            return jsonify({"error": f"API Error {response.status_code}: {response.text}"}), response.status_code
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/disconnect')
def disconnect():
    """Clear the access token and disconnect the wallet."""
    session.pop('access_token', None)
    session.pop('code_verifier', None)
    session.pop('oauth_state', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
