from flask import Flask, render_template, request, send_file, jsonify, url_for, session, redirect
import requests
import io
import os
import secrets
from functools import wraps

app = Flask(__name__)
app.secret_key = "super-secret-key-for-session"

# --- CONFIGURATION ---
# App Key from Pollinations Dashboard (pk_ - public, safe to expose)
APP_KEY = "pk_I7Juq9TCkV9jG1wL"
APP_REDIRECT_URI = "https://personamorph-ai-production.up.railway.app/callback"
POLLINATIONS_AUTHORIZE_URL = "https://gen.pollinations.ai/oauth/authorize"
POLLINATIONS_TOKEN_URL = "https://gen.pollinations.ai/oauth/token"
EDIT_API_URL = "https://gen.pollinations.ai/v1/images/edits"
DEFAULT_MODEL = "community/sharktide/inferenceport-ai-lightning-image-turbo"

# State token storage (in production, use Redis; here we use session)
# Maps state -> session_id for CSRF verification

def generate_state():
    return secrets.token_urlsafe(32)

@app.route('/')
def index():
    # Show connected state based on whether we have a token in session
    has_token = 'access_token' in session
    return render_template('index.html', logged_in=has_token)

@app.route('/connect')
def connect():
    """Initiate OAuth 2.0 Authorization Code flow with PKCE-like state."""
    state = generate_state()
    session['oauth_state'] = state
    session['redirect_after_auth'] = request.args.get('next', url_for('index'))
    
    auth_url = (
        f"{POLLINATIONS_AUTHORIZE_URL}?"
        f"client_id={APP_KEY}&"
        f"redirect_uri={APP_REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=usage&"
        f"state={state}"
    )
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
    
    # Exchange code for access token
    try:
        token_res = requests.post(
            POLLINATIONS_TOKEN_URL,
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': APP_REDIRECT_URI,
                'client_id': APP_KEY,
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
        access_token = token_data.get('access_token') or token_data.get('token')
        
        if not access_token:
            return jsonify({"error": "No access token in response", "response": token_data}), 400
        
        # Store the temporary token
        session['access_token'] = access_token
        session.pop('oauth_state', None)
        
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
    session.pop('access_token', None)
    session.pop('oauth_state', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
