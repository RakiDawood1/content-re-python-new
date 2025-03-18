import re
import os
import requests
from typing import List, Dict, Optional, Any
import time
import random
import html
import xml.etree.ElementTree as ET
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class YouTubeTranscriptFetcher:
    def __init__(self):
        """Initialize the YouTube transcript fetcher"""
        # Get API key from environment variable
        self.api_key = os.environ.get("YOUTUBE_API_KEY")
        if not self.api_key:
            print("Warning: YOUTUBE_API_KEY environment variable not found")
        
        # Create a session with retry mechanism
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """
        Create a requests session with retry mechanism
        
        Returns:
            Session with retry configuration
        """
        session = requests.Session()
        
        # Configure retry strategy
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        
        # Apply retry strategy to session
        session.mount("https://", HTTPAdapter(max_retries=retries))
        session.mount("http://", HTTPAdapter(max_retries=retries))
        
        return session
    
    def extract_video_id(self, url: str) -> Optional[str]:
        """
        Extract YouTube video ID from various URL formats
        
        Args:
            url: YouTube video URL
            
        Returns:
            Video ID or None if not found
        """
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
    
    def _get_video_caption_tracks(self, video_id: str) -> List[Dict]:
        """
        Get available captions for a video using YouTube Data API
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            List of available caption tracks
        """
        if not self.api_key:
            raise ValueError("YouTube API key is required")
        
        url = f"https://www.googleapis.com/youtube/v3/captions?part=snippet&videoId={video_id}&key={self.api_key}"
        response = requests.get(url)
        
        if response.status_code != 200:
            print(f"Error fetching captions: {response.status_code} - {response.text}")
            return []
        
        data = response.json()
        return data.get("items", [])
    
    def _get_caption_track(self, caption_id: str) -> str:
        """
        Get caption track content using YouTube Data API
        
        Args:
            caption_id: Caption track ID
            
        Returns:
            Caption track content
        """
        if not self.api_key:
            raise ValueError("YouTube API key is required")
        
        url = f"https://www.googleapis.com/youtube/v3/captions/{caption_id}?key={self.api_key}"
        
        # Note: This requires OAuth2 authentication which is beyond the scope of this example
        # For a production app, you would implement full OAuth2 flow
        # This is a limitation of the YouTube Data API - it doesn't allow anonymous access to captions
        
        # For this reason, we'll use an alternative approach...
        raise NotImplementedError("Direct caption content access requires OAuth2 authentication")
    
    def _download_subtitle(self, video_id: str, language: str = 'en') -> Optional[str]:
        """
        Alternative method to download subtitles directly using a well-known technique
        
        Args:
            video_id: YouTube video ID
            language: Language code
            
        Returns:
            Subtitle XML content or None
        """
        try:
            # First try to get the list of available captions
            list_url = f"https://www.youtube.com/api/timedtext?type=list&v={video_id}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept-Language": f"{language},en-US;q=0.9,en;q=0.8"
            }
            
            response = self.session.get(list_url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"Failed to get caption list: {response.status_code}")
                return None
                
            # Try to parse the list to find available languages
            try:
                root = ET.fromstring(response.text)
                available_langs = []
                
                for track in root.findall('.//track'):
                    lang_code = track.get('lang_code', '')
                    lang_name = track.get('name', '')
                    print(f"Found language: {lang_code} ({lang_name})")
                    available_langs.append(lang_code)
                
                # Try to use requested language, fall back to English, then any available
                target_lang = None
                if language in available_langs:
                    target_lang = language
                elif 'en' in available_langs:
                    target_lang = 'en'
                    print(f"Requested language {language} not available, falling back to English")
                elif available_langs:
                    target_lang = available_langs[0]
                    print(f"Falling back to available language: {target_lang}")
                
                if target_lang:
                    # Get the subtitle in the target language
                    subtitle_url = f"https://www.youtube.com/api/timedtext?lang={target_lang}&v={video_id}"
                    subtitle_response = self.session.get(subtitle_url, headers=headers, timeout=10)
                    
                    if subtitle_response.status_code == 200 and subtitle_response.text:
                        return subtitle_response.text
            except ET.ParseError as e:
                print(f"Error parsing caption list: {e}")
            
            # If we couldn't get the list or find the language, try direct requests
            urls_to_try = [
                f"https://www.youtube.com/api/timedtext?lang={language}&v={video_id}",
                f"https://www.youtube.com/api/timedtext?lang=en&v={video_id}",
                f"https://www.youtube.com/api/timedtext?lang={language}&v={video_id}&kind=asr",
                f"https://www.youtube.com/api/timedtext?lang=en&v={video_id}&kind=asr"
            ]
            
            for url in urls_to_try:
                print(f"Trying subtitle URL: {url}")
                try:
                    response = self.session.get(url, headers=headers, timeout=10)
                    if response.status_code == 200 and response.text and response.text.strip() != "":
                        return response.text
                except Exception as e:
                    print(f"Error fetching from {url}: {e}")
            
            return None
        except Exception as e:
            print(f"Error in download_subtitle: {e}")
            return None
    
    def _get_transcript_from_timedtext(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript using YouTube's timedtext API
        
        Args:
            video_id: YouTube video ID
            language: Language code
            
        Returns:
            List of transcript segments
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Try different formats of the timedtext API
                urls = [
                    f"https://www.youtube.com/api/timedtext?lang={language}&v={video_id}",
                    f"https://www.youtube.com/api/timedtext?lang={language}&v={video_id}&kind=asr",
                    f"https://www.youtube.com/api/timedtext?v={video_id}&lang={language}"
                ]
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                }
                
                for url in urls:
                    print(f"Trying to get transcript from: {url}")
                    response = requests.get(url, headers=headers)
                    
                    if response.status_code == 200 and response.text and response.text.strip() != "":
                        # Process XML response
                        try:
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
                                print(f"Successfully retrieved {len(segments)} transcript segments")
                                return segments
                        except ET.ParseError as e:
                            print(f"XML parse error: {e}")
                
                # If we tried all URLs and none worked, increment retry count
                retry_count += 1
                
                if retry_count < max_retries:
                    # Add jitter to backoff
                    backoff = (2 ** retry_count) * (0.5 + random.random())
                    print(f"No transcript found, retrying in {backoff:.2f} seconds (attempt {retry_count}/{max_retries})")
                    time.sleep(backoff)
            
            except Exception as e:
                print(f"Error fetching transcript: {e}")
                retry_count += 1
                
                if retry_count < max_retries:
                    backoff = retry_count * 1.5
                    print(f"Retrying in {backoff:.2f} seconds (attempt {retry_count}/{max_retries})")
                    time.sleep(backoff)
        
        # If all retries failed
        print(f"All attempts failed to find transcript for video {video_id}")
        return []
    
    def get_transcript(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript for a YouTube video
        
        Args:
            video_id: YouTube video ID
            language: Language code (default: 'en')
            
        Returns:
            List of transcript segments
        """
        print(f"Fetching transcript for video {video_id} in language {language}")
        
        # Try our direct download method first
        subtitle_xml = self._download_subtitle(video_id, language)
        
        if subtitle_xml:
            try:
                # Parse the XML
                root = ET.fromstring(subtitle_xml)
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
                    print(f"Successfully retrieved {len(segments)} transcript segments")
                    return segments
            except ET.ParseError as e:
                print(f"Error parsing subtitle XML: {e}")
        
        # If direct download failed, try the timedtext API
        segments = self._get_transcript_from_timedtext(video_id, language)
        
        if segments:
            return segments
        
        # If we have a YouTube API key, try to get caption tracks
        if self.api_key:
            try:
                tracks = self._get_video_caption_tracks(video_id)
                if tracks:
                    print(f"Found {len(tracks)} caption tracks, but direct access requires OAuth2")
            except Exception as e:
                print(f"Error getting caption tracks: {e}")
        
        # Return a fallback message as a single segment
        return [{
            "text": f"I'm sorry, the transcript for this video ({video_id}) is unavailable. The video likely doesn't have captions enabled or they're not accessible. Please try a different video with captions enabled.",
            "start": 0,
            "duration": 10,
            "isUnavailableMessage": True
        }]