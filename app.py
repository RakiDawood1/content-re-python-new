# app.py
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
import traceback

# Load environment variables
load_dotenv()

# Create the Flask app - this variable name is critical for Gunicorn
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

# Import both fetchers with different aliases (with error handling)
try:
    from youtube_hybrid_fetcher import YouTubeTranscriptFetcher as HybridFetcher
except ImportError:
    print("WARNING: youtube_hybrid_fetcher module not found!")
    # Define a placeholder class to avoid crashes
    class HybridFetcher:
        def __init__(self):
            print("WARNING: Using placeholder HybridFetcher!")
        def get_transcript(self, *args, **kwargs):
            return [{"text": "Fetcher module not available", "start": 0, "duration": 0, "isUnavailableMessage": True}]
        def extract_video_id(self, url):
            return None if not url else url.split("v=")[-1] if "v=" in url else None

try:
    from youtube_oauth_fetcher import YouTubeTranscriptFetcher as OAuthFetcher
except ImportError:
    print("WARNING: youtube_oauth_fetcher module not found!")
    # Define a placeholder class to avoid crashes
    class OAuthFetcher:
        def __init__(self):
            print("WARNING: Using placeholder OAuthFetcher!")
        def create_oauth_flow(self, *args, **kwargs):
            raise NotImplementedError("OAuth fetcher not available")
        def diagnose_transcript_access(self, *args, **kwargs):
            return {"error": "OAuth fetcher not available"}

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
    fetcher = HybridFetcher()  # Use hybrid fetcher for transcript retrieval
    transcript = fetcher.get_transcript(video_id, language)
    
    # If the transcript is just an error message, make it easier to detect
    if len(transcript) == 1 and transcript[0].get('isUnavailableMessage'):
        print(f"Transcript unavailable for video {video_id}")
        
        # Include any detailed error information in the response
        if 'errorDetails' in transcript[0]:
            print(f"Error details: {transcript[0]['errorDetails']}")
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
        
        # Use OAuthFetcher for OAuth operations
        fetcher = OAuthFetcher()
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
        
        # Use OAuthFetcher for OAuth operations
        fetcher = OAuthFetcher()
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
        fetcher = HybridFetcher()  # Use hybrid fetcher for video ID extraction
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

@app.route('/api/diagnose', methods=['POST'])
def diagnose_transcript():
    """Diagnostic endpoint to check transcript availability and troubleshoot issues"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({
                "success": False,
                "error": "YouTube URL is required",
                "message": "Please provide a valid YouTube URL in the request body"
            }), 400
        
        # Extract video ID
        fetcher = HybridFetcher()  # Use hybrid fetcher for video ID extraction
        video_id = fetcher.extract_video_id(url)
        
        if not video_id:
            return jsonify({
                "success": False,
                "error": "Invalid YouTube URL",
                "message": "Could not extract a valid YouTube video ID from the provided URL"
            }), 400
        
        # Run diagnostics - we need to use OAuthFetcher for this since diagnose_transcript_access is in that class
        oauth_fetcher = OAuthFetcher()
        diagnostics = oauth_fetcher.diagnose_transcript_access(video_id)
        
        # Add some extra info about the environment
        diagnostics["environment"] = {
            "has_api_key": bool(YOUTUBE_API_KEY),
            "has_oauth_token": bool(YOUTUBE_OAUTH_TOKEN),
            "has_client_id": bool(GOOGLE_CLIENT_ID),
            "has_client_secret": bool(GOOGLE_CLIENT_SECRET),
            "debug_mode": DEBUG
        }
        
        # Also try the standard transcript fetching method with the hybrid fetcher
        try:
            transcript = fetcher.get_transcript(video_id)
            diagnostics["standard_method"] = {
                "success": len(transcript) > 0 and not (len(transcript) == 1 and transcript[0].get('isUnavailableMessage')),
                "segments_count": len(transcript),
                "is_error_message": len(transcript) == 1 and transcript[0].get('isUnavailableMessage')
            }
        except Exception as e:
            diagnostics["standard_method"] = {
                "success": False,
                "error": str(e)
            }
        
        return jsonify({
            "success": True,
            "diagnostics": diagnostics
        })
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": "Diagnostic error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }), 500

@app.route('/api/test-captions', methods=['POST'])
def test_captions():
    """Simple test endpoint to check YouTube captions using just the Data API"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({
                "success": False,
                "error": "YouTube URL is required"
            }), 400
        
        # Extract video ID
        hybrid_fetcher = HybridFetcher()
        video_id = hybrid_fetcher.extract_video_id(url)
        
        if not video_id:
            return jsonify({
                "success": False,
                "error": "Invalid YouTube URL"
            }), 400
        
        # Try to import the simple API
        try:
            from simple_youtube_data_api import SimpleYouTubeAPI
            api_tester = SimpleYouTubeAPI()
            test_result = api_tester.test_video_caption_access(video_id)
        except ImportError:
            return jsonify({
                "success": False,
                "error": "SimpleYouTubeAPI module not found"
            }), 500
        
        return jsonify({
            "success": True,
            "test_result": test_result
        })
    
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

@app.route('/api/extract-transcript', methods=['POST'])
def extract_transcript():
    """Endpoint to extract transcript using the HTML method directly"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({
                "success": False,
                "error": "YouTube URL is required"
            }), 400
        
        # Extract video ID
        try:
            from youtube_html_fetcher import YouTubeHTMLTranscriptFetcher
            html_fetcher = YouTubeHTMLTranscriptFetcher()
        except ImportError:
            return jsonify({
                "success": False,
                "error": "HTML fetcher module not found",
                "message": "Make sure youtube_html_fetcher.py is in your project directory"
            }), 500
            
        video_id = html_fetcher.extract_video_id(url)
        
        if not video_id:
            return jsonify({
                "success": False,
                "error": "Invalid YouTube URL"
            }), 400
        
        # Get transcript
        language = data.get('language', 'en')
        transcript = html_fetcher.get_transcript(video_id, language)
        
        return jsonify({
            "success": True,
            "videoId": video_id,
            "transcript": transcript,
            "segmentCount": len(transcript),
            "isUnavailable": len(transcript) == 1 and transcript[0].get('isUnavailableMessage', False)
        })
    
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

# This ensures that the Flask app is available for Gunicorn to find
application = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=DEBUG)