# youtube_transcript_crawler.py
import re
import asyncio
import json
from typing import List, Dict, Optional, Any
from crawl4ai import AsyncWebCrawler

class YouTubeTranscriptCrawler:
    """A YouTube transcript extractor that crawls the page HTML using crawl4ai."""
    
    def extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from various URL formats."""
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
        
        # If the input is just the video ID
        if re.match(r'^[A-Za-z0-9_-]{11}$', url):
            return url
            
        return None
    
    async def get_transcript_async(self, video_id_or_url: str) -> List[Dict[str, Any]]:
        """
        Get transcript by extracting it from YouTube page HTML.
        
        Args:
            video_id_or_url: YouTube video ID or URL
            
        Returns:
            List of transcript segments
        """
        # Extract video ID if URL was provided
        video_id = self.extract_video_id(video_id_or_url)
        if not video_id:
            return self._error_response("Invalid YouTube URL or video ID")
        
        # Construct the YouTube URL
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        
        try:
            # Create extraction JS that looks for transcript data in the page HTML
            extraction_js = """
            async function extractTranscript() {
                console.log("Starting transcript extraction from page HTML");
                
                try {
                    // Method 1: Try to find transcript data in the raw HTML
                    const htmlContent = document.documentElement.outerHTML;
                    
                    // Look for transcript in initial data
                    let transcriptData = [];
                    
                    // Pattern to find transcript data in window.ytInitialData
                    const transcriptPattern = /"cueGroups":\s*(\[\{.+?\}\])/;
                    const matches = htmlContent.match(transcriptPattern);
                    
                    if (matches && matches[1]) {
                        console.log("Found potential transcript data");
                        
                        try {
                            // The regex match might not be perfect JSON, so we'll try to fix it
                            let jsonStr = matches[1]
                                .replace(/\\\\"/g, '"')
                                .replace(/\\"/g, '"')
                                .replace(/\\n/g, ' ');
                            
                            // Replace any other escaped characters
                            jsonStr = jsonStr.replace(/\\\\u([0-9a-fA-F]{4})/g, (match, p1) => {
                                return String.fromCharCode(parseInt(p1, 16));
                            });
                            
                            // Try to parse as JSON
                            const cueGroups = JSON.parse(jsonStr);
                            
                            if (Array.isArray(cueGroups)) {
                                console.log(`Found ${cueGroups.length} cue groups`);
                                
                                // Extract transcript from cueGroups structure
                                cueGroups.forEach(group => {
                                    if (group.cues) {
                                        group.cues.forEach(cue => {
                                            if (cue.startTimeMs && cue.durationMs && cue.cue && cue.cue.simpleText) {
                                                transcriptData.push({
                                                    text: cue.cue.simpleText,
                                                    start: cue.startTimeMs / 1000,
                                                    duration: cue.durationMs / 1000
                                                });
                                            }
                                        });
                                    }
                                });
                            }
                        } catch (parseError) {
                            console.error("Error parsing transcript data:", parseError);
                        }
                    }
                    
                    if (transcriptData.length > 0) {
                        console.log(`Extracted ${transcriptData.length} transcript segments from initial data`);
                        return { transcript: transcriptData };
                    }
                    
                    // Method 2: Click on transcript button and extract from panel
                    console.log("Trying to access transcript panel");
                    
                    // Try to find and click the "..." menu button
                    const moreActionsButton = document.querySelector('button[aria-label="More actions"]');
                    if (moreActionsButton) {
                        moreActionsButton.click();
                        console.log("Clicked more actions button");
                        
                        // Wait for menu to appear
                        await new Promise(resolve => setTimeout(resolve, 1000));
                        
                        // Look for "Show transcript" menu item
                        const menuItems = document.querySelectorAll('tp-yt-paper-item');
                        let foundTranscriptItem = false;
                        
                        for (const item of menuItems) {
                            const text = item.textContent.trim();
                            if (text.includes('transcript') || text.includes('Transcript')) {
                                item.click();
                                foundTranscriptItem = true;
                                console.log("Clicked show transcript");
                                break;
                            }
                        }
                        
                        if (foundTranscriptItem) {
                            // Wait for transcript panel to load
                            await new Promise(resolve => setTimeout(resolve, 2000));
                            
                            // Try to find transcript segments
                            const segmentItems = document.querySelectorAll('ytd-transcript-segment-renderer');
                            
                            if (segmentItems.length > 0) {
                                console.log(`Found ${segmentItems.length} transcript segments in panel`);
                                
                                // Extract segments
                                const segments = [];
                                
                                segmentItems.forEach(item => {
                                    const timeEl = item.querySelector('.segment-timestamp');
                                    const textEl = item.querySelector('.segment-text');
                                    
                                    if (timeEl && textEl) {
                                        // Parse timestamp (format: MM:SS)
                                        const timeStr = timeEl.textContent.trim();
                                        let seconds = 0;
                                        
                                        if (timeStr.includes(':')) {
                                            const [mins, secs] = timeStr.split(':').map(part => parseFloat(part));
                                            seconds = mins * 60 + secs;
                                        }
                                        
                                        segments.push({
                                            text: textEl.textContent.trim(),
                                            start: seconds,
                                            duration: 2.0 // Default duration
                                        });
                                    }
                                });
                                
                                // Calculate durations based on consecutive start times
                                for (let i = 0; i < segments.length - 1; i++) {
                                    segments[i].duration = segments[i+1].start - segments[i].start;
                                }
                                
                                if (segments.length > 0) {
                                    return { transcript: segments };
                                }
                            }
                        }
                    }
                    
                    return { error: "Could not find transcript data in page", transcript: [] };
                    
                } catch (error) {
                    console.error("Error extracting transcript:", error);
                    return { 
                        error: error.message || "Unknown error extracting transcript",
                        transcript: []
                    };
                }
            }
            
            return await extractTranscript();
            """
            
            # Create crawler instance
            async with AsyncWebCrawler() as crawler:
                # Run the crawler with extraction script
                result = await crawler.arun(
                    url=youtube_url,
                    js_to_execute=extraction_js,
                    # Make sure JavaScript is enabled
                    browser_config={
                        "wait_until": "networkidle2",
                        "timeout": 60000,
                        "js_enabled": True
                    }
                )
                
                # Check if extraction was successful
                if not result or not hasattr(result, 'custom_data'):
                    return self._error_response("Failed to extract data from YouTube page")
                
                # Parse the transcript data
                custom_data = result.custom_data
                if not custom_data:
                    return self._error_response("No custom data returned from extraction")
                
                transcript_data = custom_data.get('transcript', [])
                if not transcript_data:
                    error_msg = custom_data.get('error', "No transcript found")
                    return self._error_response(error_msg)
                
                return transcript_data
                
        except Exception as e:
            return self._error_response(f"Error during extraction: {str(e)}")
    
    def get_transcript(self, video_id_or_url: str) -> List[Dict[str, Any]]:
        """Synchronous wrapper for get_transcript_async."""
        return asyncio.run(self.get_transcript_async(video_id_or_url))
    
    def _error_response(self, message: str) -> List[Dict[str, Any]]:
        """Create a standardized error response."""
        return [{
            "text": message,
            "start": 0,
            "duration": 0,
            "error": True
        }]