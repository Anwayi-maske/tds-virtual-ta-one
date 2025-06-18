import requests
import time
from bs4 import BeautifulSoup
import json
from datetime import datetime

base_url = "https://discourse.onlinedegree.iitm.ac.in"
category_url = f"{base_url}/c/courses/tds-kb/34.json"

# Paste your cookie here
COOKIE = "_gcl_au=1.1.1574304078.1742879013; _ga=GA1.1.1171300002.1742879014; _fbp=fb.2.1742879013956.10823941887489488; _ga_5HTJMW67XK=GS2.1.s1749912369$o21$g0$t1749912369$j60$l0$h0; _ga_08NPRH5L4M=GS2.1.s1750148182$o42$g0$t1750148314$j60$l0$h0; _t=lt%2FxiWueNSenyoEK3Q3Y4QDEQIhdgP%2BvHL3u%2BRiIrOEVIpmaPglg9uGC9QKU56z0zXMupi8R2XC2sobaN7QsfedLH%2FEjdxf335pAKA3HUcy%2BsCia5Ws6VFyu7y0H402OYEz%2BIvYT8V0Fc4ux0j1ryf2CQfBGSGYbToXVoPKJ8H%2F%2FWe1vrdGzvpDmDw1ubVA9Z6HHcFEXWqMtqPRaiD3%2BCOvgD5iUXFCKitlsKvXHK7ZomC5QlP6CIGCI26hFknXEslf0qj2R%2B%2F9wu3s5jCQUfT8D3hxSd7Bduz6t1k7%2FJmzPU5hbIydjLkLxxHIrirrGBYoptQ%3D%3D--BbIU5HtWg0oHj43I--qiaNHu1ZL%2BKLKzyHefUSHA%3D%3D; _forum_session=OQyxYBoFfIhgoaBdlP2URTk7UNNbZWZZ4MqFkaDzOLtmAW8Vu%2B%2FEEo%2FXLDyUgIW2D4MEPdUThJtarFeLYYNMvJ5a%2BZMpY5yzqTlvBV1glV0mUpKNlIup3p8tsu%2FF5dtt1qP1JcHmkrmnkZCM6KBtrW%2FBZ3Nh2SA7pllVB7Ndef5E5fOUZNDhzKSP7R1KOum9o5%2BoR6JW7chM%2B6iXU06yGfFxYh0IemqCZHYBbbBXTJy7qVXhC7wdcHjPev%2Ba9UeagzQoznXryU38nGyVnf6Wc6K4UzvvNQ%3D%3D--MaPdzNi1PbPM3IFj--bXxb7QB7oP08m8%2BWbfyxsw%3D%3D"  # Replace with copied cookie

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Cookie": COOKIE
}

discourse_data = []

start_date = datetime(2025, 1, 1)
end_date = datetime(2025, 4, 14, 23, 59, 59)

def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    except:
        return None

try:
    session = requests.Session()
    page = 0
    while True:
        paginated_url = f"{category_url}?page={page}"
        response = session.get(paginated_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            topics = data.get("topic_list", {}).get("topics", [])
            if not topics:
                print("No more topics found")
                break
            print(f"Page {page}: Found {len(topics)} topics")

            for topic in topics:
                topic_id = topic["id"]
                slug = topic["slug"]
                created_at = parse_date(topic.get("created_at"))
                updated_at = parse_date(topic.get("updated_at"))
                if not (created_at or updated_at):
                    print(f"Skipped topic {topic_id}: Invalid date")
                    continue
                topic_date = created_at or updated_at
                if start_date <= topic_date <= end_date:
                    topic_url = f"{base_url}/t/{slug}/{topic_id}.json"
                    try:
                        topic_res = session.get(topic_url, headers=headers, timeout=10)
                        if topic_res.status_code == 200:
                            topic_json = topic_res.json()
                            posts = topic_json.get("post_stream", {}).get("posts", [])
                            for post in posts:
                                post_created = parse_date(post.get("created_at"))
                                post_updated = parse_date(post.get("updated_at"))
                                post_date = post_created or post_updated
                                if post_date and start_date <= post_date <= end_date:
                                    text = BeautifulSoup(post.get("cooked", ""), "html.parser").get_text().strip()
                                    if text:
                                        discourse_data.append({
                                            "source": "discourse",
                                            "text": text,
                                            "url": f"{base_url}/t/{slug}/{topic_id}#{post['post_number']}",
                                            "created_at": post_date.isoformat()
                                        })
                                        print(f"Fetched post {post['post_number']} in topic {topic_id}: {slug}")
                        else:
                            print(f"Failed topic {topic_id}: Status {topic_res.status_code}")
                        time.sleep(0.5)
                    except Exception as e:
                        print(f"Error topic {topic_id}: {str(e)}")
                else:
                    print(f"Skipped topic {topic_id}: Date {topic_date} outside range")
            page += 1
            time.sleep(1)
        else:
            print(f"Failed page {page}: Status {response.status_code}, Response: {response.text}")
            break
except Exception as e:
    print(f"Error category: {str(e)}")

print(f"Collected {len(discourse_data)} discourse posts")
