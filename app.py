from flask import Flask, render_template, request, send_file, jsonify
import requests
import io

app = Flask(__name__)

# --- CONFIGURATION ---
API_KEY="sk_oYoViUkYpfpeZ7hGiFzHCbblyqC7RYT1" 
DEFAULT_MODEL = "community/vendouple/uncensored-image-v2"
API_URL = "https://gen.pollinations.ai/v1/images/edits"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    
    prompt = request.form.get('prompt', 'Cyberpunk transformation')
    model = request.form.get('model', DEFAULT_MODEL)
    image_file = request.files['image']

    try:
        # Forward the request to Pollinations
        files = {"image": (image_file.filename, image_file.read(), image_file.content_type)}
        data = {"prompt": prompt, "model": model}
        headers = {"Authorization": f"Bearer {API_KEY}"}

        response = requests.post(API_URL, headers=headers, data=data, files=files, timeout=120)

        if response.status_code == 200:
            # Return the image directly to the browser
            return send_file(
                io.BytesIO(response.content),
                mimetype='image/jpeg',
                as_attachment=False
            )
        else:
            return jsonify({"error": f"API Error {response.status_code}: {response.text}"}), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
