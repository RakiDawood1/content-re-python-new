# youtube_hybrid_fetcher.py

import re
import os
import json
import html
import time
import random
import requests
import traceback
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Any
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Import our new HTML fetcher if available
try:
    from youtube_html_fetcher import YouTubeHTMLTranscriptFetcher
except ImportError:
    print("WARNING: youtube_html_fetcher not found. HTML extraction method will be unavailable.")

class YouTubeTranscriptFetcher:
    def __init__(self):
        """Initialize the YouTube transcript fetcher with multiple approaches"""
        # Get API keys from environment variables
        self.api_key = os.environ.get("YOUTUBE_API_KEY")
        self.rapidapi_key = os.environ.get("RAPIDAPI_KEY")
        
        # Create a session with retry mechanism
        self.session = self._create_session()
        
        # Create an instance of the HTML fetcher if available
        self.html_fetcher = None
        try:
            self.html_fetcher = YouTubeHTMLTranscriptFetcher()
        except (NameError, ImportError):
            print("HTML fetcher not available, will use other methods")
        
        # Track errors for debugging
        self.errors = []
    
    def _create_session(self) -> requests.Session:
        """Create a session with retry mechanism"""
        session = requests.Session()
        
        # Configure retry strategy
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        
        # Apply retry strategy
        session.mount("https://", HTTPAdapter(max_retries=retries))
        session.mount("http://", HTTPAdapter(max_retries=retries))
        
        # Set common headers
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        })
        
        return session
    
    def extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from various URL formats"""
        if self.html_fetcher:
            return self.html_fetcher.extract_video_id(url)
            
        # Fallback implementation if HTML fetcher not available
        if not url:
            return None
        
        # Standard YouTube URL format
        standard_pattern = r'^.*((youtu.be\/)|(v\/)|(\/u\/\w\/)|(embed\/)|(watch\?))\??v?=?([^#&?]*)'
        match = re.search(standard_pattern, url)
        if match and match.group(7) and len(match.group(7)) == 11:
            return match.group(7)
        
        # YouTube Shorts format
        shorts_pattern = r'^.*((youtube.com\/shorts\/)([^#&?]*))'
        match = re.search(shorts_pattern, url)
        if match and match.group(3):
            return match.group(3)
        
        return None
    
    def get_transcript(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript using multiple methods, with detailed error tracking
        
        Args:
            video_id: YouTube video ID
            language: Language code (default: 'en')
            
        Returns:
            List of transcript segments
        """
        print(f"Fetching transcript for video {video_id} in language {language}")
        
        # Reset errors list
        self.errors = []
        
        # Try multiple methods in sequence
        transcript = None
        methods = [
            # New HTML method is now our first choice
            self._method_html,
            self._method_direct_timedtext,
            self._method_direct_timedtext_asr, 
            self._method_invidious,
            self._method_rapidapi,
            self._method_gotranscript,
            self._method_youtube_data_api
        ]
        
        for method in methods:
            method_name = method.__name__.replace("_method_", "")
            try:
                print(f"Trying method: {method_name}")
                transcript = method(video_id, language)
                
                if transcript:
                    print(f"Successfully retrieved transcript using {method_name}")
                    return transcript
                
            except Exception as e:
                error_info = {
                    "method": method_name,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }
                self.errors.append(error_info)
                print(f"Error with {method_name}: {e}")
        
        # If all methods failed, return the error message
        print(f"All transcript methods failed for video {video_id}")
        
        # Compile error information for debugging
        error_details = ""
        for error in self.errors:
            error_details += f"Method {error['method']}: {error['error']}\n"
        
        # Return a detailed fallback message
        return [{
            "text": f"I'm sorry, the transcript for this video ({video_id}) is unavailable. The video likely doesn't have captions enabled or they're not accessible. Please try a different video with captions enabled.",
            "start": 0,
            "duration": 10,
            "isUnavailableMessage": True,
            "errorDetails": error_details
        }]
    
    def _method_html(self, video_id: str, language: str) -> List[Dict[str, Any]]:
        """Try to get transcript using the HTML extraction method"""
        if not self.html_fetcher:
            print("HTML fetcher not available, skipping method")
            return None
            
        return self.html_fetcher.get_transcript(video_id, language)
    
    def _method_direct_timedtext(self, video_id: str, language: str) -> List[Dict[str, Any]]:
        """Try to get transcript using YouTube's timedtext API"""
        url = f"https://www.youtube.com/api/timedtext?lang={language}&v={video_id}"
        
        response = self.session.get(url, timeout=10)
        if response.status_code != 200 or not response.text or response.text.strip() == "":
            return None
        
        try:
            # Parse XML
            root = ET.fromstring(response.text)
            segments = []
            
            for text in root.findall('.//text'):
                start = float(text.get('start', 0))
                duration = float(text.get('dur', 0))
                content = text.text or ''
                
                # Unescape HTML entities
                if '&' in content:
                    content = html.unescape(content)
                
                segments.append({
                    "text": content.strip(),
                    "start": start,
                    "duration": duration
                })
            
            if segments:
                return segments
        except ET.ParseError:
            pass
        
        return None
    
    def _method_direct_timedtext_asr(self, video_id: str, language: str) -> List[Dict[str, Any]]:
        """Try to get auto-generated transcript"""
        url = f"https://www.youtube.com/api/timedtext?lang={language}&v={video_id}&kind=asr"
        
        response = self.session.get(url, timeout=10)
        if response.status_code != 200 or not response.text or response.text.strip() == "":
            return None
        
        try:
            # Parse XML
            root = ET.fromstring(response.text)
            segments = []
            
            for text in root.findall('.//text'):
                start = float(text.get('start', 0))
                duration = float(text.get('dur', 0))
                content = text.text or ''
                
                # Unescape HTML entities
                if '&' in content:
                    content = html.unescape(content)
                
                segments.append({
                    "text": content.strip(),
                    "start": start,
                    "duration": duration
                })
            
            if segments:
                return segments
        except ET.ParseError:
            pass
        
        return None
    
    def _method_invidious(self, video_id: str, language: str) -> List[Dict[str, Any]]:
        """Try to get transcript using Invidious instances"""
        instances = [
            "https://invidious.snopyta.org",
            "https://yewtu.be",
            "https://vid.puffyan.us",
            "https://invidious.kavin.rocks"
        ]
        
        random.shuffle(instances)
        
        for instance in instances[:2]:  # Only try the first 2 random instances
            try:
                url = f"{instance}/api/v1/captions/{video_id}"
                response = self.session.get(url, timeout=10)
                
                if response.status_code != 200:
                    continue
                
                data = response.json()
                captions = data.get("captions", [])
                
                if not captions:
                    continue
                
                # Find the right language caption
                caption_url = None
                for caption in captions:
                    if caption.get("language_code") == language:
                        caption_url = caption.get("url")
                        break
                
                # Try English or any available
                if not caption_url:
                    for caption in captions:
                        if caption.get("language_code") == "en":
                            caption_url = caption.get("url")
                            break
                
                if not caption_url and captions:
                    caption_url = captions[0].get("url")
                
                if caption_url:
                    content_response = self.session.get(caption_url, timeout=10)
                    if content_response.status_code == 200:
                        transcript_data = content_response.json()
                        segments = []
                        
                        for item in transcript_data:
                            segments.append({
                                "text": item.get("text", ""),
                                "start": item.get("start", 0),
                                "duration": item.get("duration", 0)
                            })
                        
                        if segments:
                            return segments
            except:
                continue
        
        return None
    
    def _method_rapidapi(self, video_id: str, language: str) -> List[Dict[str, Any]]:
        """Try to get transcript using RapidAPI"""
        if not self.rapidapi_key:
            return None
        
        try:
            url = "https://youtube-transcript-api.p.rapidapi.com/retrieve"
            
            querystring = {"video_id": video_id, "language": language}
            
            headers = {
                "X-RapidAPI-Key": self.rapidapi_key,
                "X-RapidAPI-Host": "youtube-transcript-api.p.rapidapi.com"
            }
            
            response = requests.get(url, headers=headers, params=querystring, timeout=15)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            if not isinstance(data, list):
                return None
            
            segments = []
            for item in data:
                segments.append({
                    "text": item.get("text", ""),
                    "start": item.get("start", 0),
                    "duration": item.get("duration", 0)
                })
            
            if segments:
                return segments
            
        except:
            pass
        
        return None
    
    def _method_gotranscript(self, video_id: str, language: str) -> List[Dict[str, Any]]:
        """Try using another transcript API service"""
        try:
            url = f"https://gotranscript.com/api/show-video-cc/{video_id}"
            
            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                return None
            
            data = response.json()
            if not data.get("success") or not data.get("items"):
                return None
            
            segments = []
            for item in data.get("items", []):
                segments.append({
                    "text": item.get("caption", ""),
                    "start": item.get("startTime", 0),
                    "duration": item.get("duration", 0)
                })
            
            if segments:
                return segments
        except:
            pass
        
        return None
    
    def _method_youtube_data_api(self, video_id: str, language: str) -> List[Dict[str, Any]]:
        """
        Try to use the YouTube Data API if we have an API key
        This will only check if captions exist but can't download them without OAuth
        """
        if not self.api_key:
            return None
        
        try:
            url = f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails&id={video_id}&key={self.api_key}"
            
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                return None
            
            data = response.json()
            items = data.get("items", [])
            
            if not items:
                return None
            
            # Get caption flag (only tells us if captions exist, not their content)
            has_captions = items[0].get("contentDetails", {}).get("caption", "").lower() == "true"
            
            if has_captions:
                # We know captions exist, but we can't get them without OAuth
                # At least we can return a more helpful error message
                return [{
                    "text": f"This video ({video_id}) has captions available, but accessing them requires YouTube OAuth authentication which is not configured correctly. Please try a different fetching method or contact the developer.",
                    "start": 0, 
                    "duration": 10,
                    "isUnavailableMessage": True,
                    "hasCaptions": True,
                    "requiresOAuth": True
                }]
        except Exception as e:
            print(f"YouTube Data API error: {e}")
        
        return None