import re
import json
import requests

def extract_transcript_direct(video_id):
    """Extract captions directly from YouTube page HTML - simplified version"""
    print(f"Attempting to extract transcript for {video_id}")
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Failed to fetch YouTube page: HTTP {response.status_code}")
        return None
    
    html_content = response.text
    print(f"Got HTML content, length: {len(html_content)}")
    
    # Find player response data
    player_response_pattern = r'ytInitialPlayerResponse\s*=\s*({.+?});'
    match = re.search(player_response_pattern, html_content)
    
    if not match:
        print("Failed to find player response data in HTML")
        return None
    
    print("Found player response data")
    player_response = json.loads(match.group(1))
    
    # Extract captions data
    caption_tracks = player_response.get('captions', {}).get('playerCaptionsTracklistRenderer', {}).get('captionTracks', [])
    
    if not caption_tracks:
        print("No caption tracks found in player response data")
        return None
    
    # Log available languages
    available_langs = [f"{track.get('languageCode')} ({track.get('name', {}).get('simpleText', 'Unknown')})" 
                      for track in caption_tracks]
    print(f"Available caption tracks: {', '.join(available_langs)}")
    
    # Find English or first available caption
    base_url = None
    for track in caption_tracks:
        track_lang = track.get('languageCode')
        if track_lang == 'en' or base_url is None:
            base_url = track.get('baseUrl')
            print(f"Selected track: {track_lang}")
            if track_lang == 'en':
                break
    
    if not base_url:
        print("No usable caption track URL found")
        return None
    
    print(f"Caption base URL: {base_url}")
    
    # Get caption JSON
    caption_url = f"{base_url}&fmt=json3"
    caption_response = requests.get(caption_url, headers=headers)
    
    if caption_response.status_code != 200:
        print(f"Failed to fetch caption JSON: HTTP {caption_response.status_code}")
        return None
    
    print("Got caption JSON data")
    caption_data = caption_response.json()
    events = caption_data.get('events', [])
    
    segments = []
    for event in events:
        if 'segs' not in event:
            continue
        
        start = event.get('tStartMs', 0) / 1000
        duration = event.get('dDurationMs', 0) / 1000
        
        text_parts = []
        for seg in event.get('segs', []):
            if 'utf8' in seg:
                text_parts.append(seg['utf8'])
        
        if text_parts:
            segments.append({
                "text": ''.join(text_parts).strip(),
                "start": start,
                "duration": duration
            })
    
    print(f"Extracted {len(segments)} transcript segments")
    
    # Print a few samples
    if segments:
        print("\nSample segments:")
        for i, segment in enumerate(segments[:3]):
            print(f"  {i+1}. [{segment['start']:.2f}s]: {segment['text']}")
    
    return segments

# Test with the Rick Astley video
transcript = extract_transcript_direct("dQw4w9WgXcQ")
if transcript:
    print(f"\nSuccessfully extracted {len(transcript)} segments")
else:
    print("\nFailed to extract transcript")