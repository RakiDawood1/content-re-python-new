from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import json
import requests
import time
from functools import wraps
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# API configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

# In-memory cache (would use Redis or another solution in production)
transcript_cache = {}
blog_cache = {}

# Import the ThirdPartyTranscriptFetcher class
from third_party_transcript_fetcher import ThirdPartyTranscriptFetcher

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
    fetcher = ThirdPartyTranscriptFetcher()
    return fetcher.get_transcript(video_id, language)

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
    url = 'https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent'   
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
        "timestamp": datetime.now().isoformat()
    })

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
                    "generateBlog": "Boolean, generate blog post",
                    "fallbackMessage": "Boolean, provide fallback message for unavailable transcripts",
                    "debug": "Boolean, return debugging information"
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
        fallback_message = data.get('fallbackMessage', True)
        
        if not url:
            return jsonify({
                "success": False,
                "error": "YouTube URL is required",
                "message": "Please provide a valid YouTube URL in the request body"
            }), 400
        
        # Extract video ID
        fetcher = ThirdPartyTranscriptFetcher()
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
        except Exception as e:
            print(f"Transcript fetch error: {e}")
            
            # If fallback message is enabled, create a placeholder transcript
            if fallback_message:
                transcript = [{
                    "text": f"I'm sorry, the transcript for this video ({video_id}) is unavailable. The video likely doesn't have captions enabled or they're not accessible. Please try a different video with captions enabled.",
                    "start": 0,
                    "duration": 10,
                    "isUnavailableMessage": True
                }]
                result["transcript"] = transcript
                result["transcriptUnavailable"] = True
                result["error"] = str(e)
            else:
                return jsonify({
                    "success": False,
                    "error": "Transcript unavailable",
                    "message": f"Unable to retrieve transcript: {e}",
                    "videoId": video_id
                }), 404
        
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
                return jsonify({
                    "success": False,
                    "error": "Blog generation failed",
                    "message": str(blog_error),
                    "transcript": result.get("transcript")
                }), 500
        
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