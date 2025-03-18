from flask import Flask, request, jsonify, redirect, url_for, session
from flask_cors import CORS
from dotenv import load_dotenv
import os
import json
import requests
import time
import uuid
from functools import wraps
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", str(uuid.uuid4()))
CORS(app)  # Enable CORS for all routes

# If you need specific CORS settings for your Webflow site
CORS(app, origins=["https://portfolio-1-dee95f.webflow.io"])

# API configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

# OAuth configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
YOUTUBE_OAUTH_TOKEN = os.environ.get("YOUTUBE_OAUTH_TOKEN")

# Set expected environment variables for the OAuth fetcher
os.environ["GOOGLE_CLIENT_ID"] = GOOGLE_CLIENT_ID if GOOGLE_CLIENT_ID else ""
os.environ["GOOGLE_CLIENT_SECRET"] = GOOGLE_CLIENT_SECRET if GOOGLE_CLIENT_SECRET else ""
os.environ["YOUTUBE_OAUTH_TOKEN"] = YOUTUBE_OAUTH_TOKEN if YOUTUBE_OAUTH_TOKEN else ""

# In-memory cache 
transcript_cache = {}

# Import the transcript fetcher
from youtube_oauth_fetcher import YouTubeTranscriptFetcher

def get_cache_key(video_id, language):
    """Generate a cache key from video ID and language"""
    return f"{video_id}:{language}"

def cache_transcript(func):
    """Decorator to cache transcript results"""
    @wraps(func)
    def wrapper(video_id, language, *args, **kwargs):
        cache_key = get_cache_key(video_id, language)
        
        # Check if in cache and not expired
        if cache_key in transcript_cache:
            cached_item = transcript_cache[cache_key]
            if datetime.now() < cached_item['expires']:
                print(f"Cache hit for transcript {video_id}")
                return cached_item['data']
        
        # Not in cache or expired, call the function
        result = func(video_id, language, *args, **kwargs)
        
        # Store in cache with 24-hour expiration
        transcript_cache[cache_key] = {
            'data': result,
            'expires': datetime.now() + timedelta(hours=24)
        }
        
        return result
    return wrapper

@cache_transcript
def fetch_transcript(video_id, language):
    """Fetch transcript with caching"""
    fetcher = YouTubeTranscriptFetcher()
    transcript = fetcher.get_transcript(video_id, language)
    
    # If the transcript is just an error message, make it easier to detect
    if len(transcript) == 1 and transcript[0].get('isUnavailableMessage'):
        print(f"Transcript unavailable for video {video_id}")
    else:
        print(f"Successfully fetched transcript with {len(transcript)} segments")
    
    return transcript

def generate_blog(transcript, video_id):
    """Generate a blog post from transcript using Gemini API"""
    # Skip if this is an unavailable message
    if len(transcript) == 1 and transcript[0].get('isUnavailableMessage'):
        return {
          "title": "Transcript Unavailable",
          "content": "Unable to generate a blog post because the transcript is unavailable for this video.",
          "videoId": video_id,
          "generatedAt": datetime.now().isoformat(),
          "wordCount": 0
        }
    
    # Extract the full text from the transcript
    full_text = ' '.join([segment['text'] for segment in transcript])
    
    if not full_text.strip():
        return {
            "title": "Empty Transcript",
            "content": "Unable to generate a blog post because the transcript is empty.",
            "videoId": video_id,
            "generatedAt": datetime.now().isoformat(),
            "wordCount": 0
        }
    
    # Create the prompt for Gemini
    prompt = f"""
I have a YouTube video transcript that I want to convert into a well-formatted blog post.
Please create a blog post that captures the key points, maintains the tone and style of the original,
and is organized with proper headings, paragraphs, and flow.

The transcript is from a YouTube video (ID: {video_id}) and appears to be about:
{full_text[:300]}...

Here's the full transcript:
{full_text}

Please format the blog post with:
1. An engaging title
2. A brief introduction
3. Properly structured sections with headings
4. A conclusion
5. Maintain the same tone and voice as the original content

The blog post should be comprehensive but concise, highlighting the main points rather than including every detail.
"""
    
    # Call Gemini API
    url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent'   
    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }]
    }
    
    headers = {
        'Content-Type': 'application/json',
        'x-goog-api-key': GEMINI_API_KEY
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code != 200:
        error_data = response.json()
        raise Exception(f"Gemini API error: {error_data.get('error', {}).get('message', response.status_code)}")
    
    data = response.json()
    blog_content = data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text')
    
    if not blog_content:
        raise Exception('Empty response from Gemini API')
    
    # Extract title from the generated content (assuming the first line is the title)
    lines = blog_content.split('\n')
    title = lines[0]
    
    # Remove markdown heading symbols if present (e.g., # Title)
    if title.startswith('#'):
        title = title.lstrip('#').strip()
    
    # Remove any quotes if present
    title = title.strip('"\'')
    
    return {
        "title": title,
        "content": blog_content,
        "videoId": video_id,
        "generatedAt": datetime.now().isoformat(),
        "wordCount": len(blog_content.split())
    }

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "api_keys": {
            "gemini": bool(GEMINI_API_KEY),
            "youtube": bool(YOUTUBE_API_KEY),
            "oauth": bool(YOUTUBE_OAUTH_TOKEN)
        }
    })

@app.route('/oauth/init', methods=['GET'])
def oauth_init():
    """Initialize OAuth flow"""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return jsonify({
            "success": False,
            "error": "OAuth configuration missing",
            "message": "Google client ID and secret are required for OAuth"
        }), 400
        
    try:
        # Create the OAuth flow
        base_url = request.url_root.rstrip('/')
        redirect_uri = f"{base_url}/oauth2callback"
        
        fetcher = YouTubeTranscriptFetcher()
        flow = fetcher.create_oauth_flow(redirect_uri)
        
        # Generate authorization URL
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        # Store state in session
        session['state'] = state
        
        # Redirect to authorization URL
        return redirect(authorization_url)
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": "OAuth initialization failed",
            "message": str(e)
        }), 500

@app.route('/oauth2callback')
def oauth2callback():
    """Handle OAuth callback"""
    if 'state' not in session:
        return jsonify({
            "success": False,
            "error": "Invalid state",
            "message": "OAuth state missing from session"
        }), 400
        
    try:
        # Create the OAuth flow
        base_url = request.url_root.rstrip('/')
        redirect_uri = f"{base_url}/oauth2callback"
        
        fetcher = YouTubeTranscriptFetcher()
        flow = fetcher.create_oauth_flow(redirect_uri)
        
        # Use the authorization code to get credentials
        flow.fetch_token(authorization_response=request.url)
        
        # Get credentials
        credentials = flow.credentials
        
        # Store credentials
        token_data = fetcher.store_credentials(credentials)
        
        # Display token to add to environment variables
        return f"""
        <html>
        <body>
            <h1>YouTube API OAuth Successful</h1>
            <p>Authentication successful! Add the following token to your environment variables as YOUTUBE_OAUTH_TOKEN:</p>
            <textarea rows="10" cols="80" onclick="this.select()">{token_data}</textarea>
            <p>After adding this token to your environment, restart your application.</p>
        </body>
        </html>
        """
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": "OAuth callback failed",
            "message": str(e)
        }), 500

@app.route('/api/process', methods=['POST', 'OPTIONS'])
def process_youtube():
    """Process YouTube URL to get transcript and generate blog"""
    # Handle CORS preflight request
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.json
        
        # Check for debug requests
        if data.get('debug'):
            return jsonify({
                "success": True,
                "message": "Debug information",
                "environment": {
                    "hasGeminiApiKey": bool(GEMINI_API_KEY),
                    "hasYouTubeApiKey": bool(YOUTUBE_API_KEY),
                    "hasOAuthToken": bool(YOUTUBE_OAUTH_TOKEN),
                    "debug": DEBUG
                },
                "timestamp": datetime.now().isoformat()
            })
        
        # Check for health check
        if data.get('healthCheck'):
            return jsonify({
                "success": True,
                "message": "API is operational",
                "timestamp": datetime.now().isoformat()
            })
        
        # Check for documentation request
        if data.get('docs'):
            return jsonify({
                "success": True,
                "message": "API Documentation",
                "endpoint": "/api/process",
                "method": "POST",
                "parameters": {
                    "url": "YouTube video URL (required)",
                    "language": "Language code, defaults to 'en'",
                    "generateBlog": "Boolean, generate blog post"
                },
                "oauth": {
                    "setup": "Visit /oauth/init to set up OAuth for YouTube API",
                    "required": "OAuth is required to access YouTube transcripts reliably"
                },
                "example": {
                    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "language": "en", 
                    "generateBlog": True
                }
            })
        
        # Get parameters
        url = data.get('url')
        language = data.get('language', 'en')
        should_generate_blog = data.get('generateBlog', True)
        
        if not url:
            return jsonify({
                "success": False,
                "error": "YouTube URL is required",
                "message": "Please provide a valid YouTube URL in the request body"
            }), 400
        
        # Check if OAuth is set up
        if not YOUTUBE_OAUTH_TOKEN:
            # Still proceed, but add a warning
            print("Warning: YouTube OAuth token is not configured. Transcript fetching may be unreliable.")
        
        # Extract video ID
        fetcher = YouTubeTranscriptFetcher()
        video_id = fetcher.extract_video_id(url)
        
        if not video_id:
            return jsonify({
                "success": False,
                "error": "Invalid YouTube URL",
                "message": "Could not extract a valid YouTube video ID from the provided URL"
            }), 400
        
        # Set up response data
        result = {
            "success": True,
            "videoId": video_id,
            "processingTime": datetime.now().isoformat()
        }
        
        # Fetch transcript
        start_time = time.time()
        try:
            transcript = fetch_transcript(video_id, language)
            result["transcript"] = transcript
            print(f"Fetched {len(transcript)} transcript segments in {time.time() - start_time:.2f}s")
            
            # Check if the transcript is actually available
            if len(transcript) == 1 and transcript[0].get('isUnavailableMessage'):
                result["transcriptUnavailable"] = True
                
                # Add OAuth setup message if not configured
                if not YOUTUBE_OAUTH_TOKEN:
                    result["oauthMissing"] = True
                    result["oauthSetupUrl"] = url_for('oauth_init', _external=True)
        except Exception as e:
            print(f"Transcript fetch error: {e}")
            result["error"] = str(e)
            result["transcriptUnavailable"] = True
            return jsonify(result), 500
        
        # Generate blog if requested
        if should_generate_blog and GEMINI_API_KEY:
            try:
                blog = generate_blog(transcript, video_id)
                result["blog"] = blog
                
                # Add a note if this was generated from a fallback message
                if result.get("transcriptUnavailable"):
                    blog["note"] = "This blog was generated without an actual video transcript. The content is based on a generic message as the video's transcript was unavailable."
            except Exception as blog_error:
                print(f"Blog generation error: {blog_error}")
                result["error"] = str(blog_error)
                result["blogGenerationFailed"] = True
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Unhandled error: {e}")
        return jsonify({
            "success": False,
            "error": "Server error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=DEBUG)