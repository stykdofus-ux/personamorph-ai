from flask import Flask, render_template, request, send_file, jsonify, url_for, session, redirect
import requests
import io
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = "super-secret-key-for-session"

# --- CONFIGURATION ---
# Default fallback model
DEFAULT_MODEL = "community/sharktide/inferenceport-ai-lightning-image-turbo" 
API_URL = "https://gen.pollinations.ai/v1/images/edits"

@app.route('/')
def index():
    return render_template('index.html', logged_in= 'user_key' in session)

@app.route('/set_key', methods=['POST'])
def set_key():
    key = request.form.get('api_key')
    if not key or not key.startswith('sk_'):
        return jsonify({"error": "Invalid API key. Must start with 'sk_'"}), 400
    
    # Simple validation check to see if the key works
    try:
        res = requests.get("https://gen.pollinations.ai/v1/models", headers={"Authorization": f"Bearer {key}"})
        if res.status_code != 200:
            return jsonify({"error": "API key is invalid or unauthorized"}), 401
    except:
        return jsonify({"error": "Connection to Pollinations failed"}), 500

    session['user_key'] = key
    return jsonify({"success": True})

@app.route('/logout')
def logout():
    session.pop('user_key', None)
    return redirect(url_for('index'))

@app.route('/generate', methods=['POST'])
def generate():
    if 'user_key' not in session:
        return jsonify({"error": "Please enter your API key first"}), 401
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
