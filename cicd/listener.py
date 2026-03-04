import subprocess
import hmac
import hashlib
import os
from flask import Flask, request, abort

app = Flask(__name__)

# Webhook Secret set in GitHub repository settings
# Recommended to store this in your .env file for security
WEBHOOK_SECRET = os.environ.get('GITHUB_WEBHOOK_SECRET', 'your_super_secret_string')

@app.route('/webhook', methods=['POST'])
def handle_github_webhook():
    # 1. Verify that the request is actually from GitHub using the signature
    signature = request.headers.get('X-Hub-Signature-256')
    if not signature:
        abort(400, 'Signature header is missing!')

    # Calculate the HMAC hash from the request body using the secret
    sha_name, signature_hash = signature.split('=', 1)
    if sha_name != 'sha256':
        abort(400, 'Invalid signature algorithm!')

    mac = hmac.new(WEBHOOK_SECRET.encode('utf-8'), msg=request.data, digestmod=hashlib.sha256)
    
    # 2. Compare the calculated hash with the provided signature
    if not hmac.compare_digest(mac.hexdigest(), signature_hash):
        print("Invalid webhook signature detected. Aborting.")
        abort(403, 'Invalid signature.')
        
    # --- Branch Verification Logic ---
    try:
        payload = request.json
        # GitHub provides the branch info in the "ref" field (e.g., "refs/heads/main")
        ref = payload.get('ref', '')
        
        # Only proceed if the push happened on the 'main' branch
        if not ref.endswith('main'):
            print(f"Push to {ref} ignored. Waiting for push to main.")
            return 'Ignored (wrong branch)', 200
    except Exception as e:
        print(f"Error parsing payload: {e}")
    # ------------------------------------

    # 3. If everything is valid, trigger the update script
    print("Valid GitHub push received to main. Starting update script...")
    # Run update.sh in the background to avoid blocking the response
    subprocess.Popen(['~/summary-bot-gemini/cicd/update.sh'])
    
    return 'OK', 200

if __name__ == '__main__':
    # Listen on port 5000
    app.run(host='0.0.0.0', port=5000)
