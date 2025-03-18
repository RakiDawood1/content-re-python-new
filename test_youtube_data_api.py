# test_youtube_data_api.py
import os
import json
import sys
from youtube_data_api_captions import YouTubeDataAPITranscriptFetcher

def test_youtube_data_api():
    # Create the fetcher
    fetcher = YouTubeDataAPITranscriptFetcher()
    
    # Accept command line argument for a specific video ID to test
    if len(sys.argv) > 1:
        test_videos = [sys.argv[1]]
        print(f"Testing specific video ID: {test_videos[0]}")
    else:
        # List of videos to test (use some popular videos known to have captions)
        test_videos = [
            "9bZkp7q19f0",  # Gangnam Style
            "dQw4w9WgXcQ",  # Rick Astley - Never Gonna Give You Up
            "8UVNT4wvIGY",  # Gotye - Somebody That I Used to Know
            "rYEDA3JcQqw",  # Adele - Rolling in the Deep
            "TcMBFSGVi1c"   # Avengers: Endgame Trailer
        ]
    
    for video_id in test_videos:
        print(f"\n{'='*50}")
        print(f"Testing video {video_id}")
        print(f"{'='*50}")
        
        try:
            # First, get available caption tracks
            caption_tracks = fetcher.get_caption_tracks(video_id)
            
            print(f"Found {len(caption_tracks)} caption tracks")
            
            # Print caption track details
            for i, track in enumerate(caption_tracks):
                snippet = track.get('snippet', {})
                print(f"\nTrack {i+1}:")
                print(f"  Language: {snippet.get('language', 'unknown')}")
                print(f"  Track kind: {snippet.get('trackKind', 'unknown')}")
                print(f"  Last updated: {snippet.get('lastUpdated', 'unknown')}")
                print(f"  Track ID: {track.get('id', 'unknown')}")
                
            # Now get the transcript
            transcript = fetcher.get_transcript(video_id)
            
            # Print some sample segments
            print(f"\nGot {len(transcript)} segments")
            
            # Check if it's an error message
            if len(transcript) == 1 and transcript[0].get('isUnavailableMessage'):
                print("Got unavailable message:")
                print(f"- {transcript[0]['text']}")
            else:
                # Print first few segments
                print("First 3 segments:")
                for i, segment in enumerate(transcript[:3]):
                    print(f"  {i+1}. [{segment['start']:.2f}s]: {segment['text']}")
                
                # Print some middle segments if available
                mid_point = len(transcript) // 2
                if len(transcript) > 6:
                    print("\nMiddle 3 segments:")
                    for i, segment in enumerate(transcript[mid_point:mid_point+3]):
                        print(f"  {mid_point+i+1}. [{segment['start']:.2f}s]: {segment['text']}")
            
            # Success
            print(f"\n✅ Success for video {video_id}")
            
        except Exception as e:
            print(f"❌ Failed for video {video_id}: {e}")

if __name__ == "__main__":
    test_youtube_data_api()