"""
Test the cache functionality of the YouTube Summarizer API.

This script tests:
1. Cache hit for summaries
2. Cache hit for translations
3. Retrieving cache status
"""
import requests
import json
import time

# API key for testing - replace with a valid key if needed
API_KEY = "test_api_key"

# Base URL for the API
BASE_URL = "http://localhost:8181"

def test_summary_caching():
    """Test that summaries are properly cached and retrieved from cache."""
    print("Testing summary caching...")
    
    # Define test video URL
    video_url = "https://www.youtube.com/watch?v=xWTA5HPPWBs"
    
    # First request - should process and store in cache
    response1 = requests.post(
        f"{BASE_URL}/api/summarize",
        headers={"x-api-key": API_KEY},
        json={"youtube_url": video_url}
    )
    
    # Check if the request was successful
    if response1.status_code != 200:
        print(f"Error: {response1.status_code} - {response1.text}")
        return False
        
    result1 = response1.json()
    cached1 = result1.get("cached", False)
    print(f"First request - Cached: {cached1}")
    
    # Second request - should retrieve from cache
    response2 = requests.post(
        f"{BASE_URL}/api/summarize",
        headers={"x-api-key": API_KEY},
        json={"youtube_url": video_url}
    )
    
    # Check if the request was successful and cached
    if response2.status_code != 200:
        print(f"Error: {response2.status_code} - {response2.text}")
        return False
        
    result2 = response2.json()
    cached2 = result2.get("cached", False)
    print(f"Second request - Cached: {cached2}")
    
    # Compare the results
    if not cached2:
        print("ERROR: Second request should be cached!")
        return False
    
    print("Summary caching test passed!")
    return True

def test_translation_caching():
    """Test that translations are properly cached and retrieved from cache."""
    print("\nTesting translation caching...")
    
    # Define test video ID and language
    video_id = "xWTA5HPPWBs"
    target_language = "Spanish"
    
    # First request - should process and store in cache
    response1 = requests.post(
        f"{BASE_URL}/api/translate",
        headers={"x-api-key": API_KEY},
        json={"video_id": video_id, "target_language": target_language}
    )
    
    # Check if the request was successful
    if response1.status_code != 200:
        print(f"Error: {response1.status_code} - {response1.text}")
        return False
        
    result1 = response1.json()
    cached1 = result1.get("cached", False)
    print(f"First request - Cached: {cached1}")
    
    # Second request - should retrieve from cache
    response2 = requests.post(
        f"{BASE_URL}/api/translate",
        headers={"x-api-key": API_KEY},
        json={"video_id": video_id, "target_language": target_language}
    )
    
    # Check if the request was successful and cached
    if response2.status_code != 200:
        print(f"Error: {response2.status_code} - {response2.text}")
        return False
        
    result2 = response2.json()
    cached2 = result2.get("cached", False)
    print(f"Second request - Cached: {cached2}")
    
    # Compare the results
    if not cached2:
        print("ERROR: Second request should be cached!")
        return False
    
    print("Translation caching test passed!")
    return True

def test_cache_status():
    """Test retrieving cache status."""
    print("\nTesting cache status...")
    
    # Request cache status
    response = requests.get(
        f"{BASE_URL}/api/cache_status",
        headers={"x-api-key": API_KEY}
    )
    
    # Check if the request was successful
    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}")
        return False
        
    result = response.json()
    print(f"Cache status:")
    print(f"  Cached summaries: {result.get('cached_summaries')}")
    print(f"  Cached translations: {result.get('cached_translations')}")
    
    print("Cache status test passed!")
    return True

def main():
    """Run all tests."""
    print("Starting cache tests...")
    
    # Run tests
    summary_success = test_summary_caching()
    translation_success = test_translation_caching()
    status_success = test_cache_status()
    
    # Print summary
    print("\nTest Summary:")
    print(f"  Summary caching: {'PASSED' if summary_success else 'FAILED'}")
    print(f"  Translation caching: {'PASSED' if translation_success else 'FAILED'}")
    print(f"  Cache status: {'PASSED' if status_success else 'FAILED'}")

if __name__ == "__main__":
    main()
