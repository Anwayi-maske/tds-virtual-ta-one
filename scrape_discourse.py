import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json

def scrape_discourse(start_date, end_date, base_url="https://discourse.onlinedegree.iitm.ac.in"):
    """Scrape Discourse posts from a date range."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    threads = []
    page = 1
    while True:
        response = requests.get(f"{base_url}/latest.json?page={page}")
        if response.status_code != 200:
            break
        data = response.json()
        for topic in data.get("topic_list", {}).get("topics", []):
            created_at = datetime.strptime(topic.get("created_at", "")[:10], "%Y-%m-%d")
            if start <= created_at <= end:
                thread = {
                    "title": topic.get("title", ""),
                    "id": topic.get("id", ""),
                    "slug": topic.get("slug", ""),
                    "posts": []
                }
                post_response = requests.get(f"{base_url}/t/{thread['id']}.json")
                if post_response.status_code == 200:
                    post_data = post_response.json()
                    for post in post_data.get("post_stream", {}).get("posts", []):
                        thread["posts"].append({
                            "post_number": post.get("post_number", ""),
                            "cooked": post.get("cooked", ""),
                            "created_at": post.get("created_at", "")
                        })
                threads.append(thread)
        page += 1
        if not data.get("topic_list", {}).get("more_topics_url", ""):
            break
    return threads

if __name__ == "__main__":
    threads = scrape_discourse("2025-01-01", "2025-04-14")
    with open("discourse_data.json", "w") as f:
        json.dump(threads, f, indent=4)
    print("Scraped data saved to discourse_data.json")