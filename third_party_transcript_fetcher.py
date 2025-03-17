import re
from typing import List, Dict, Optional, Any
from youtube_transcript_api import YouTubeTranscriptApi

class ThirdPartyTranscriptFetcher:
    def __init__(self):
        """Initialize the transcript fetcher using the youtube-transcript-api"""
        pass
    
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
    
    def get_transcript(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript for a YouTube video using youtube-transcript-api
        
        Args:
            video_id: YouTube video ID
            language: Language code (default: 'en')
            
        Returns:
            List of transcript segments
            
        Raises:
            Exception: If transcript cannot be retrieved
        """
        print(f"Fetching transcript for video {video_id} in language {language}")
        
        try:
            # Try to get transcript in the specified language
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            try:
                # First try to find the exact language match
                transcript = transcript_list.find_transcript([language])
            except:
                try:
                    # If that fails, try to find a transcript with the language code as prefix
                    # For example, if language='en', try to find 'en-US', 'en-GB', etc.
                    matching_transcripts = [t for t in transcript_list if t.language_code.startswith(language)]
                    if matching_transcripts:
                        transcript = matching_transcripts[0]
                    else:
                        # Fall back to the first available transcript
                        transcript = transcript_list.find_transcript([])
                except:
                    # If all else fails, try to get any generated transcript and translate it
                    transcript = transcript_list.find_generated_transcript()
                    transcript = transcript.translate(language)
            
            # Get the transcript data
            transcript_data = transcript.fetch()
            
            # Format the transcript in our expected format
            segments = []
            for entry in transcript_data:
                segments.append({
                    "text": entry['text'],
                    "start": entry['start'],
                    "duration": entry.get('duration', 0)
                })
            
            return segments
            
        except Exception as e:
            print(f"Error fetching transcript: {e}")
            raise Exception(f"Failed to get transcript for video {video_id}: {str(e)}")