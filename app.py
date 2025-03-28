# app.py
from flask import Flask, request, jsonify
import asyncio
import json
import re
import os
from crawl4ai import AsyncWebCrawler
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

app = Flask(__name__)

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

@app.route('/youtube', methods=['POST'])
def youtube_endpoint():
    """
    Process a YouTube URL and return metadata and transcript.
    
    Expected JSON input:
    {
        "url": "https://www.youtube.com/watch?v=VIDEO_ID"
    }
    """
    try:
        data = request.json
        
        # Check if URL is provided
        if not data or 'url' not in data:
            return jsonify({
                "success": False,
                "error": "Missing URL",
                "message": "Please provide a YouTube video URL"
            }), 400
        
        video_url = data['url']
        
        # Extract video ID
        video_id = extract_video_id(video_url)
        if not video_id:
            return jsonify({
                "success": False,
                "error": "Invalid URL",
                "message": "Could not extract YouTube video ID from URL"
            }), 400
        
        # Process the video
        result = asyncio.run(crawl_youtube_with_api(video_url))
        
        if result:
            return jsonify({
                "success": True,
                "data": result
            })
        else:
            return jsonify({
                "success": False,
                "error": "Processing failed",
                "message": "Failed to process YouTube video"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "An error occurred while processing the request"
        }), 500

async def crawl_youtube_with_api(video_url):
    """
    Crawl YouTube video metadata with crawl4ai and extract transcript with youtube-transcript-api.
    
    Args:
        video_url: URL of the YouTube video
    """
    # Extract video ID from URL
    video_id = extract_video_id(video_url)
    if not video_id:
        return None
    
    # Create tasks for both crawling and transcript extraction
    metadata_task = crawl_for_metadata(video_url)
    transcript_task = extract_transcript(video_id)
    
    # Run both tasks
    metadata, transcript = await asyncio.gather(metadata_task, transcript_task)
    
    # Combine results
    result = {
        "video_id": video_id,
        "video_url": video_url,
        "metadata": metadata,
        "transcript": transcript
    }
    
    return result

def extract_video_id(url):
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([^&\s]+)',
        r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([^\?\s]+)',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([^\?\s]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

async def crawl_for_metadata(video_url):
    """Use crawl4ai to extract metadata from YouTube video page."""
    try:
        # Configure browser settings
        browser_config = {
            "timeout": 30000,  # 30 second timeout
            "js_enabled": True  # Enable JavaScript
        }
        
        # Run the crawler
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(
                url=video_url,
                browser_config=browser_config,
                verbose=True
            )
            
            # Extract metadata
            metadata = {}
            
            if hasattr(result, 'metadata') and result.metadata:
                # Copy relevant metadata
                for key in ['title', 'description', 'author', 'og:title', 'og:description', 
                            'og:image', 'og:video', 'og:video:tag']:
                    if key in result.metadata:
                        metadata[key] = result.metadata[key]
            
            # Extract more metadata from page content if available
            if hasattr(result, 'html') and result.html:
                # Try to extract channel name
                channel_match = re.search(r'"ownerChannelName":"([^"]+)"', result.html)
                if channel_match:
                    metadata['channel'] = channel_match.group(1)
                
                # Try to extract view count
                views_match = re.search(r'"viewCount":"(\d+)"', result.html)
                if views_match:
                    metadata['views'] = int(views_match.group(1))
                
                # Try to extract like count
                likes_match = re.search(r'"likeCount":"(\d+)"', result.html)
                if likes_match:
                    metadata['likes'] = int(likes_match.group(1))
                
                # Try to extract publish date
                date_match = re.search(r'"publishDate":"([^"]+)"', result.html)
                if date_match:
                    metadata['publish_date'] = date_match.group(1)
            
            return metadata
            
    except Exception as e:
        print(f"Error during metadata crawling: {str(e)}")
        return {}

async def extract_transcript(video_id):
    """Use youtube-transcript-api to extract transcript."""
    # Create a coroutine to run the synchronous YouTube API in a separate thread
    async def get_transcript_async():
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, get_transcript, video_id)
    
    return await get_transcript_async()

def get_transcript(video_id):
    """Synchronous function to get transcript using youtube-transcript-api."""
    try:
        # Get available transcripts
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try to get English transcript first
        try:
            transcript = transcript_list.find_transcript(['en'])
        except:
            # If English not available, get the first available transcript
            transcript = transcript_list.find_transcript([])
        
        # Get the actual transcript data
        transcript_data = transcript.fetch()
        
        return {
            "success": True,
            "language": transcript.language,
            "is_generated": transcript.is_generated,
            "segments": transcript_data
        }
        
    except TranscriptsDisabled:
        return {
            "success": False,
            "error": "Transcripts are disabled for this video"
        }
        
    except NoTranscriptFound:
        return {
            "success": False,
            "error": "No transcript found for this video"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)