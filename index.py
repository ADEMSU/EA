from flask import Flask, request, jsonify, render_template
import os
import sys

# Add the root directory to the path so we can import from other modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import your main application modules
try:
    import main
except ImportError:
    pass

app = Flask(__name__)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    """Handle all routes and return a simple response for now"""
    return jsonify({
        "status": "success",
        "message": "Your Flask app is running on Vercel!",
        "path": path
    })

# This is required for Vercel serverless deployment
if __name__ == '__main__':
    app.run(debug=True)
