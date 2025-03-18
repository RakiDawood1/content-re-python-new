import os
import re
import requests
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv
import html
import xml.etree.ElementTree as ET
import json
import time

class YouTubeTranscriptFetcher:
    def __init__(self):
        """Initialize the YouTube transcript fetcher"""
        # Load environment variables
        load_dotenv()
        
        # Get API key
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
    
    def get_transcript_using_innertube(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript using YouTube's InnerTube API (used by the frontend)
        
        Args:
            video_id: YouTube video ID
            language: Language code (default: 'en')
            
        Returns:
            List of transcript segments or error message
        """
        try:
            # First, we need to get the initial config data from the video page
            print("Trying to get transcript using InnerTube API approach")
            
            # Get the video page
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept-Language": f"{language},en-US;q=0.9,en;q=0.8"
            }
            
            video_page = requests.get(video_url, headers=headers)
            
            # Quick check to see if the video exists
            if "Video unavailable" in video_page.text:
                raise Exception("Video does not exist or is private")
            
            # Try to extract potential URLs from the HTML for debugging
            transcript_url_pattern = r'"captionTracks":\[(.*?)\]'
            match = re.search(transcript_url_pattern, video_page.text)
            
            if match:
                caption_tracks_json = "[" + match.group(1) + "]"
                
                # Try to fix JSON if needed (replace single quotes, fix trailing commas)
                caption_tracks_json = caption_tracks_json.replace("'", "\"")
                caption_tracks_json = re.sub(r',\s*}', '}', caption_tracks_json)
                caption_tracks_json = re.sub(r',\s*]', ']', caption_tracks_json)
                
                try:
                    caption_tracks = json.loads(caption_tracks_json)
                    
                    if caption_tracks:
                        print(f"Found {len(caption_tracks)} caption tracks:")
                        
                        # Find a suitable track
                        suitable_track = None
                        
                        # First try to find the requested language
                        for track in caption_tracks:
                            track_lang = track.get("languageCode")
                            is_auto = track.get("kind") == "asr"
                            
                            print(f"- {track_lang} (Auto-generated: {is_auto})")
                            
                            if track_lang == language:
                                suitable_track = track
                                print(f"Found exact language match: {language}")
                                break
                        
                        # If no exact match, take any available track
                        if not suitable_track and caption_tracks:
                            suitable_track = caption_tracks[0]
                            print(f"No exact match found. Using {suitable_track.get('languageCode')}")
                        
                        if suitable_track:
                            # Extract the URL
                            base_url = suitable_track.get("baseUrl")
                            
                            if base_url:
                                # Sometimes, the URL contains HTML entities
                                base_url = html.unescape(base_url)
                                
                                # Add format=json3 to get JSON format
                                if "?" in base_url:
                                    transcript_url = f"{base_url}&fmt=json3"
                                else:
                                    transcript_url = f"{base_url}?fmt=json3"
                                
                                print(f"Requesting transcript from: {transcript_url}")
                                
                                # Get the transcript
                                transcript_response = requests.get(transcript_url, headers=headers)
                                
                                if transcript_response.status_code == 200:
                                    transcript_data = transcript_response.json()
                                    
                                    # Parse the JSON transcript
                                    events = transcript_data.get("events", [])
                                    segments = []
                                    
                                    for event in events:
                                        # Skip events without text segments
                                        if "segs" not in event:
                                            continue
                                            
                                        start_time = event.get("tStartMs", 0) / 1000
                                        duration = (event.get("dDurationMs", 0) / 1000) if "dDurationMs" in event else 0
                                        
                                        # Combine all segments in this event
                                        text_parts = []
                                        for seg in event.get("segs", []):
                                            if "utf8" in seg:
                                                text_parts.append(seg["utf8"])
                                        
                                        if text_parts:
                                            text = "".join(text_parts).strip()
                                            if text:  # Only add non-empty segments
                                                segments.append({
                                                    "text": text,
                                                    "start": start_time,
                                                    "duration": duration
                                                })
                                    
                                    if segments:
                                        print(f"Successfully retrieved {len(segments)} transcript segments")
                                        return segments
                except Exception as e:
                    print(f"Error parsing caption tracks: {e}")
            
            raise Exception("Could not find caption tracks in the video page")
            
        except Exception as e:
            print(f"Error using InnerTube approach: {e}")
            return None
    
    def get_transcript(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript for a YouTube video trying multiple methods
        
        Args:
            video_id: YouTube video ID
            language: Language code (default: 'en')
            
        Returns:
            List of transcript segments
            
        Raises:
            Exception: If transcript cannot be retrieved
        """
        print(f"Fetching transcript for video {video_id} in language {language}")
        
        # Try the InnerTube approach first (more reliable)
        transcript = self.get_transcript_using_innertube(video_id, language)
        
        if transcript:
            return transcript
        
        # If InnerTube failed, try the timedtext API as fallback
        try:
            # Try the timedtext API approach
            transcript_url = f"https://www.youtube.com/api/timedtext?lang={language}&v={video_id}"
            print(f"Requesting transcript from: {transcript_url}")
            response = requests.get(transcript_url, timeout=10)
            
            # Check if we got a valid response
            if response.status_code != 200 or not response.text or response.text.strip() == "":
                # Try to get the transcript list
                list_url = f"https://www.youtube.com/api/timedtext?type=list&v={video_id}"
                list_response = requests.get(list_url, timeout=10)
                
                # If we got a list of available transcripts
                if list_response.status_code == 200 and list_response.text and list_response.text.strip() != "":
                    try:
                        # Parse the list response
                        list_root = ET.fromstring(list_response.text)
                        
                        # Find available languages
                        available_langs = []
                        for track in list_root.findall('.//track'):
                            lang_code = track.get('lang_code', '')
                            lang_name = track.get('name', '')
                            print(f"Found language: {lang_code} ({lang_name})")
                            available_langs.append(lang_code)
                        
                        # Try to find the requested language, or fall back to any available language
                        target_lang = language if language in available_langs else (available_langs[0] if available_langs else None)
                        
                        if target_lang:
                            lang_url = f"https://www.youtube.com/api/timedtext?lang={target_lang}&v={video_id}"
                            response = requests.get(lang_url, timeout=10)
                        else:
                            raise Exception("No transcripts available for this video")
                    except Exception as e:
                        print(f"Error parsing transcript list: {e}")
                        raise Exception(f"Failed to parse transcript list: {e}")
                else:
                    # Try auto-generated captions as a last resort
                    asr_url = f"https://www.youtube.com/api/timedtext?lang={language}&v={video_id}&kind=asr"
                    asr_response = requests.get(asr_url, timeout=10)
                    
                    if asr_response.status_code == 200 and asr_response.text and asr_response.text.strip() != "":
                        response = asr_response
                    else:
                        raise Exception("No transcripts or auto-captions available for this video")
            
            # Try to parse the XML
            try:
                transcript_root = ET.fromstring(response.text)
            except ET.ParseError as e:
                print(f"XML parse error: {e}")
                raise Exception(f"Failed to parse transcript XML: {e}")
            
            # Extract transcript segments
            segments = []
            for text in transcript_root.findall('.//text'):
                start = float(text.get('start', 0))
                duration = float(text.get('dur', 0))
                content = text.text or ''
                
                # Unescape HTML entities if present
                if '&' in content:
                    content = html.unescape(content)
                
                segments.append({
                    "text": content,
                    "start": start,
                    "duration": duration
                })
            
            if not segments:
                raise Exception("Transcript parsed successfully but no text segments found")
            
            print(f"Successfully retrieved {len(segments)} transcript segments")
            return segments
            
        except Exception as e:
            print(f"Error fetching transcript: {e}")
            
            # Return a fallback message as a single segment
            return [{
                "text": f"I'm sorry, the transcript for this video ({video_id}) is unavailable. The video likely doesn't have captions enabled or they're not accessible. Please try a different video with captions enabled.",
                "start": 0,
                "duration": 10,
                "isUnavailableMessage": True
            }]