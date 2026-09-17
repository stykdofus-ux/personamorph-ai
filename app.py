from flask import Flask, render_template, request, send_file, jsonify, url_for
import requests
import io
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = "super-secret-key-for-session"

# --- CONFIGURATION ---
API_KEY="sk_oYoViUkYpfpeZ7hGiFzHCbblyqC7RYT1" 
DEFAULT_MODEL = "epic-manga" # FIXED: Now using a valid edit model
API_URL = "https://gen.pollinations.ai/v1/images/edits"

@app.route('/')
def index():
    return render_template('index.html', logged_in= 'user_key' in session)

@app.route('/login')
def login():
    # Step 1: Redirect user to Pollinations OAuth page
    # Note: Redirect URI must match exactly what is in the Pollinations Dashboard
    redirect_uri = request.url_root + "callback"
    auth_url = f"https://gen.pollinations.ai/oauth/authorize?client_id=pk_I7Juq9TCkV9jG1wL&redirect_uri={redirect_uri}&response_type=code&scope=usage"
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "Authorization failed", 400

    token_res = requests.post("https://gen.pollinations.ai/oauth/token", data={
        "client_id": "pk_I7Juq9TCkV9jG1wL",
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": request.url_root + "callback"
    })

    if token_res.status_code == 200:
        token_data = token_res.json()
        session['user_key'] = token_data.get('access_token')
        return redirect(url_for('index'))
    
    return f"Token exchange failed: {token_res.text}", 400

@app.route('/logout')
def logout():
    session.pop('user_key', None)
    return redirect(url_for('index'))

@app.route('/generate', methods=['POST'])
def generate():
    if 'user_key' not in session:
        return jsonify({"error": "Please login first"}), 401
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    
    prompt = request.form.get('prompt', 'Cyberpunk transformation')
    model = request.form.get('model', DEFAULT_MODEL)
    image_file = request.files['image']
    user_key = session['user_key']

    try:
        files = {"image": (image_file.filename, image_file.read(), image_file.content_type)}
        data = {"prompt": prompt, "model": model}
        headers = {"Authorization": f"Bearer {user_key}"}

        response = requests.post(API_URL, headers=headers, data=data, files=files, timeout=120)

        if response.status_code == 200:
            # The API might return b64_json or raw binary depending on the model
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
