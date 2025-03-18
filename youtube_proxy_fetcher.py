import re
import os
import requests
import json
from typing import List, Dict, Optional, Any
import time
import random
from urllib.parse import quote

class YouTubeTranscriptFetcher:
    def __init__(self):
        """Initialize the YouTube transcript fetcher"""
        # Get API key from environment variable
        self.api_key = os.environ.get("YOUTUBE_API_KEY")
        if not self.api_key:
            print("Warning: YOUTUBE_API_KEY environment variable not found")
    
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
    
    def _get_transcript_from_rapidapi(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Try to get transcript using a third-party API service
        
        This example uses YoutubeTranscript API from RapidAPI, which acts as a proxy
        and handles YouTube rate limiting
        
        Note: You'll need to sign up for a RapidAPI key at:
        https://rapidapi.com/ytdlfree/api/youtube-v31
        """
        
        # Check if we have the RapidAPI key
        rapid_api_key = os.environ.get("RAPIDAPI_KEY")
        if not rapid_api_key:
            print("RAPIDAPI_KEY environment variable not found, skipping RapidAPI approach")
            return []
            
        try:
            url = "https://youtube-v31.p.rapidapi.com/captions"
            
            querystring = {"part":"snippet","videoId":video_id}
            
            headers = {
                "X-RapidAPI-Key": rapid_api_key,
                "X-RapidAPI-Host": "youtube-v31.p.rapidapi.com"
            }
            
            print(f"Fetching transcript via RapidAPI for video {video_id}")
            response = requests.get(url, headers=headers, params=querystring)
            
            if response.status_code != 200:
                print(f"RapidAPI error: {response.status_code} - {response.text}")
                return []
                
            data = response.json()
            captions = data.get("items", [])
            
            if not captions:
                print("No captions found via RapidAPI")
                return []
                
            # Find the right language caption
            caption_id = None
            for caption in captions:
                caption_language = caption.get("snippet", {}).get("language", "")
                is_auto = caption.get("snippet", {}).get("trackKind") == "ASR"
                
                if caption_language == language:
                    caption_id = caption.get("id")
                    print(f"Found exact language match: {language}")
                    break
                    
            # If no exact match, try English or any available
            if not caption_id:
                for caption in captions:
                    caption_language = caption.get("snippet", {}).get("language", "")
                    if caption_language == "en":
                        caption_id = caption.get("id")
                        print("Using English caption as fallback")
                        break
                        
            # If still no caption, take the first one
            if not caption_id and captions:
                caption_id = captions[0].get("id")
                print("Using first available caption")
                
            if not caption_id:
                print("No usable caption ID found")
                return []
                
            # Unfortunately, RapidAPI doesn't provide the actual transcript content
            # We know it exists, but we'd need to implement a different approach to get it
            # For this example, let's assume we found captions but can't access the content
            
            print("Caption found but content can't be accessed via this API")
            return []
            
        except Exception as e:
            print(f"Error with RapidAPI approach: {e}")
            return []
    
    def _get_transcript_from_ytapi(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Try to get transcript using a different third-party service
        This example uses a free subtitle API proxy
        """
        try:
            # Try API 1: YtSub API
            url = f"https://ytsub.herokuapp.com/api/transcript?id={video_id}&lang={language}"
            print(f"Trying YtSub API: {url}")
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    segments = []
                    for item in data:
                        segments.append({
                            "text": item.get("text", ""),
                            "start": item.get("start", 0),
                            "duration": item.get("dur", 0)
                        })
                    
                    if segments:
                        print(f"Successfully retrieved {len(segments)} transcript segments from YtSub API")
                        return segments
            
            # Try API 2: Another subtitles API
            url = f"https://yt.lemnoslife.com/subtitles?video_id={video_id}&language={language}"
            print(f"Trying Lemnos API: {url}")
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                subtitles = data.get("items", [])
                
                if subtitles:
                    segments = []
                    for item in subtitles:
                        segments.append({
                            "text": item.get("text", ""),
                            "start": item.get("start", 0),
                            "duration": item.get("dur", 0)
                        })
                    
                    if segments:
                        print(f"Successfully retrieved {len(segments)} transcript segments from Lemnos API")
                        return segments
            
            return []
            
        except Exception as e:
            print(f"Error with ytapi approach: {e}")
            return []
    
    def _get_transcript_from_invidious(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Try to get transcript using Invidious public instances
        Invidious is an alternative front-end to YouTube
        """
        # List of public Invidious instances
        instances = [
            "https://invidious.snopyta.org",
            "https://yewtu.be",
            "https://invidious.kavin.rocks",
            "https://vid.puffyan.us",
            "https://invidious.namazso.eu",
            "https://inv.riverside.rocks"
        ]
        
        random.shuffle(instances)  # Randomize to distribute load
        
        for instance in instances[:3]:  # Try up to 3 random instances
            try:
                url = f"{instance}/api/v1/captions/{video_id}"
                print(f"Trying Invidious instance: {url}")
                
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    captions = data.get("captions", [])
                    
                    # Find the right language caption
                    caption_url = None
                    for caption in captions:
                        if caption.get("language_code") == language:
                            caption_url = caption.get("url")
                            print(f"Found exact language match: {language}")
                            break
                    
                    # If no exact match, try English or any available
                    if not caption_url:
                        for caption in captions:
                            if caption.get("language_code") == "en":
                                caption_url = caption.get("url")
                                print("Using English caption as fallback")
                                break
                    
                    # If still no caption, take the first one
                    if not caption_url and captions:
                        caption_url = captions[0].get("url")
                        print("Using first available caption")
                    
                    if caption_url:
                        # Get the actual transcript content
                        content_response = requests.get(caption_url, timeout=10)
                        if content_response.status_code == 200:
                            try:
                                transcript_data = content_response.json()
                                segments = []
                                
                                for item in transcript_data:
                                    segments.append({
                                        "text": item.get("text", ""),
                                        "start": item.get("start", 0),
                                        "duration": item.get("duration", 0)
                                    })
                                
                                if segments:
                                    print(f"Successfully retrieved {len(segments)} transcript segments from Invidious")
                                    return segments
                            except json.JSONDecodeError:
                                print("Error decoding transcript JSON from Invidious")
            
            except Exception as e:
                print(f"Error with Invidious instance {instance}: {e}")
        
        return []
    
    def _try_gotranscript_api(self, video_id: str) -> List[Dict[str, Any]]:
        """Try to use another transcript API service"""
        try:
            url = f"https://gotranscript.com/api/show-video-cc/{video_id}"
            print(f"Trying GoTranscript API: {url}")
            
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("success") and data.get("items"):
                        segments = []
                        for item in data.get("items", []):
                            segments.append({
                                "text": item.get("caption", ""),
                                "start": item.get("startTime", 0),
                                "duration": item.get("duration", 0)
                            })
                        
                        if segments:
                            print(f"Successfully retrieved {len(segments)} transcript segments from GoTranscript")
                            return segments
                except:
                    print("Error parsing GoTranscript response")
        except Exception as e:
            print(f"Error with GoTranscript API: {e}")
        
        return []
    
    def get_transcript(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript for a YouTube video using multiple methods
        
        Args:
            video_id: YouTube video ID
            language: Language code (default: 'en')
            
        Returns:
            List of transcript segments
        """
        print(f"Fetching transcript for video {video_id} in language {language}")
        
        # Try different approaches to get the transcript
        
        # 1. Try Invidious API
        segments = self._get_transcript_from_invidious(video_id, language)
        if segments:
            return segments
            
        # 2. Try direct third-party API services
        segments = self._get_transcript_from_ytapi(video_id, language)
        if segments:
            return segments
            
        # 3. Try RapidAPI if key is available
        segments = self._get_transcript_from_rapidapi(video_id, language)
        if segments:
            return segments
            
        # 4. Try GoTranscript API
        segments = self._try_gotranscript_api(video_id)
        if segments:
            return segments
            
        # If we have a YouTube API key, we could try using it directly
        # But this is likely to fail without OAuth2
        if self.api_key:
            print("Note: Using the YouTube API directly to get transcripts requires OAuth2 authentication")
        
        # Return a fallback message as a single segment
        return [{
            "text": f"I'm sorry, the transcript for this video ({video_id}) is unavailable. The video likely doesn't have captions enabled or they're not accessible. Please try a different video with captions enabled.",
            "start": 0,
            "duration": 10,
            "isUnavailableMessage": True
        }]