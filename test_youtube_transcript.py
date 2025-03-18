# test_api_fetcher.py
from youtube_transcript_api_fetcher import YouTubeTranscriptFetcher
import json
import sys

def test_transcript_fetcher():
    # Create the fetcher
    fetcher = YouTubeTranscriptFetcher()
    
    # Accept command line argument for a specific video ID to test
    if len(sys.argv) > 1:
        test_videos = [sys.argv[1]]
        print(f"Testing specific video ID: {test_videos[0]}")
    else:
        # List of videos to test (videos known to have good captions)
        test_videos = [
            "8S0FDjFBj8o",  # TED Talk (likely has good captions)
            "jNQXAC9IVRw",  # First YouTube video ever
            "9bZkp7q19f0",  # Gangnam Style
            "dQw4w9WgXcQ",  # Rick Astley - Never Gonna Give You Up
            "TvXm6HInpeU"   # Another TED Talk
        ]
    
    for video_id in test_videos:
        print(f"\n{'='*50}")
        print(f"Testing video {video_id}")
        print(f"{'='*50}")
        
        try:
            # Get the transcript
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
                
                # Print total transcript length
                total_text = ' '.join([segment['text'] for segment in transcript])
                print(f"\nTotal transcript length: {len(total_text)} characters")
            
            # Success
            print(f"\n✅ Success for video {video_id}")
            
        except Exception as e:
            print(f"❌ Failed for video {video_id}: {e}")

if __name__ == "__main__":
    test_transcript_fetcher()