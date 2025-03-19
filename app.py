# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import traceback
from youtube_transcript_crawler import YouTubeTranscriptCrawler

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Create the transcript crawler
crawler = YouTubeTranscriptCrawler()

@app.route('/health', methods=['GET'])
def health_check_root():
    """Health check endpoint at root path"""
    return jsonify({
        "status": "ok"
    })

@app.route('/api/health', methods=['GET'])
def health_check_api():
    """Health check endpoint at /api/health path for Render"""
    return jsonify({
        "status": "ok"
    })

@app.route('/transcript', methods=['POST'])
def get_transcript():
    """Get transcript for a YouTube video"""
    try:
        # Get the video URL or ID from the request
        data = request.json
        video_url = data.get('url')
        
        if not video_url:
            return jsonify({
                "success": False,
                "error": "Missing URL",
                "message": "Please provide a YouTube video URL"
            }), 400
        
        # Get the transcript
        transcript = crawler.get_transcript(video_url)
        
        # Check if there was an error
        if transcript and len(transcript) == 1 and transcript[0].get('error'):
            return jsonify({
                "success": False,
                "error": transcript[0].get('text'),
                "transcript": []
            }), 400
        
        # Return the transcript
        return jsonify({
            "success": True,
            "transcript": transcript
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)