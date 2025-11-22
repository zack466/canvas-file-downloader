#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "playwright",
#     "requests",
# ]
# ///

import os
import re
import time
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright
import requests

# --- INSTRUCTIONS ---
#
# 1. Fill in this variable with your Canvas domain
#
CANVAS_DOMAIN = "XXX.instructure.com"  # FILL IN
#
# 2. Open the CANVAS_DOMAIN in your browser, go to the "Storage" tab of the
#    developer tools, and click on the canvas url. Copy the cookie values for
#    _csrf_token, log_session_id, and canvas_session into the cookies list
#    below. If you access Canvas in any other tab while the scraper is running,
#    or it might stop working.
#
COOKIES = [
    {
        "name": "_csrf_token",
        "value": "PASTE HERE",
        "domain": CANVAS_DOMAIN,
        "path": "/",
    },
    {
        "name": "log_session_id",
        "value": "PASTE HERE",
        "domain": CANVAS_DOMAIN,
        "path": "/",
    },
    {
        "name": "canvas_session",
        "value": "PASTE HERE",
        "domain": CANVAS_DOMAIN,
        "path": "/",
    },
]
#
# 3. Change any of the following config variables if you want, and then run this script.
#
DOWNLOAD_DIR = "./files"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) Gecko/20100101 Firefox/140.0"
#
# --- END INSTRUCTIONS ---

BASE_URL = f"https://{CANVAS_DOMAIN}"
DIRECT_MEDIA_EXTS = ('.mp4', '.mp3', '.wav', '.m4a', '.mov', '.avi', '.webm', '.mkv')

def sanitize_filename(name):
    """Removes illegal characters from filenames/folder names."""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def get_requests_cookies():
    """Converts Playwright cookie list to a dict for requests."""
    return {c['name']: c['value'] for c in COOKIES}

def is_direct_media_file(url):
    """
    Returns True ONLY if the URL actually looks like a downloadable file 
    (ends in .mp4, etc). Filters out YouTube/Vimeo players.
    """
    if not url: return False
    parsed = urlparse(url)
    return parsed.path.lower().endswith(DIRECT_MEDIA_EXTS)

def download_resource(url, folder_path, session):
    """Downloads a file using requests."""
    try:
        with session.get(url, stream=True, allow_redirects=True) as r:
            r.raise_for_status()

            # 1. Try Content-Disposition header
            filename = None
            if "Content-Disposition" in r.headers:
                cd = r.headers["Content-Disposition"]
                f_match = re.findall(r'filename="?([^"]+)"?', cd)
                if f_match:
                    filename = f_match[0]

            # 2. Fallback: Extract from URL
            if not filename:
                path = urlparse(r.url).path
                filename = os.path.basename(unquote(path))

            # 3. Last Resort
            if not filename or filename == 'download':
                filename = f"resource_{int(time.time())}.dat"

            filename = sanitize_filename(filename)
            file_path = os.path.join(folder_path, filename)

            if os.path.exists(file_path):
                print(f"      [Skip] Exists: {filename}")
                return

            print(f"      [Downloading] {filename}...")

            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

    except Exception as e:
        print(f"      [!] Download failed for {url}: {e}")

def normalize_file_url(url, course_id):
    match = re.search(r'/files/(\d+)', url)
    if match:
        file_id = match.group(1)
        return f"{BASE_URL}/courses/{course_id}/files/{file_id}/download?download_frd=1"
    return url

def is_external_url(url):
    if not url: return False
    parsed = urlparse(url)
    return parsed.netloc and "instructure.com" not in parsed.netloc

def is_media_url(url):
    """Identifies potential media URLs (both files and players)."""
    if not url: return False
    # Check extensions
    if url.lower().endswith(DIRECT_MEDIA_EXTS + ('.m3u8',)):
        return True
    # Check common hosts
    media_hosts = ['youtube.com', 'youtu.be', 'vimeo.com', 'instructuremedia.com', 'panopto.com', 'zoom.us', 'kaltura.com']
    parsed = urlparse(url)
    if any(host in parsed.netloc for host in media_hosts):
        return True
    return False

def scrape_media_robust(page):
    """Finds media in main page and frames."""
    media_found = set()

    try:
        page.wait_for_selector("video, audio, iframe", timeout=1000)
    except: pass

    # Direct tags
    for tag in page.locator("video, audio").all():
        src = tag.get_attribute("src")
        if src: media_found.add(src)

    # Source tags
    for tag in page.locator("video source, audio source").all():
        src = tag.get_attribute("src")
        if src: media_found.add(src)

    # Iframes
    for frame in page.frames:
        try:
            for tag in frame.locator("video source, audio source").all():
                src = tag.get_attribute("src")
                if src: media_found.add(src)
            for tag in frame.locator("video, audio").all():
                src = tag.get_attribute("src")
                if src: media_found.add(src)
        except: continue

    return media_found

def get_course_content(page, course_id):
    base_course_url = f"{BASE_URL}/courses/{course_id}"
    queue = {base_course_url, f"{base_course_url}/modules", f"{base_course_url}/files"}
    visited = set()

    files_found = set()
    external_links = set()
    media_found = set()

    while queue:
        url = queue.pop()
        if url in visited: continue
        visited.add(url)

        print(f"    Scanning: {url}")

        try:
            response = page.goto(url, wait_until='networkidle')
            final_url = page.url

            # 1. Handle Redirects
            if "/files/" in final_url and ("download" in final_url or re.search(r'/files/\d+', final_url)):
                files_found.add(normalize_file_url(final_url, course_id))
                continue

            if is_external_url(final_url):
                if is_media_url(final_url):
                    media_found.add(final_url)
                else:
                    external_links.add(final_url)
                continue

            # 2. Wait for content
            try:
                if "/pages/" in final_url or "/assignments/" in final_url:
                    page.wait_for_selector("div.user_content, div#wiki_page_show", timeout=3000)
            except: pass

            # 3. Scrape Media
            page_media = scrape_media_robust(page)
            for m in page_media:
                if not m.startswith(('blob:', 'javascript:')):
                    media_found.add(m)

            # 4. Scrape Links
            hrefs = page.evaluate("""() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)""")
            for full_url in hrefs:
                if not full_url or full_url.startswith(('javascript:', 'mailto:', '#', 'tel:')): continue
                if '{{' in full_url: continue

                if "/files/" in full_url:
                    files_found.add(normalize_file_url(full_url, course_id))
                elif is_external_url(full_url):
                    if is_media_url(full_url):
                        media_found.add(full_url)
                    else:
                        external_links.add(full_url)
                else:
                    parsed = urlparse(full_url)
                    if f"/courses/{course_id}" in parsed.path:
                        if re.search(r'/(assignments|discussion_topics|modules/items|announcements|pages)/', parsed.path):
                            clean_next = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                            if clean_next not in visited:
                                queue.add(clean_next)

        except Exception as e:
            print(f"    [!] Error on {url}: {e}")

    return list(files_found), list(external_links), list(media_found)

def process_course(page, course_id, course_name):
    print(f"\n=== Processing Course: {course_name} ({course_id}) ===")

    # 1. Setup Directory
    safe_name = sanitize_filename(course_name)
    course_dir = os.path.join(DOWNLOAD_DIR, safe_name)
    if not os.path.exists(course_dir):
        os.makedirs(course_dir)

    # 2. Scrape
    files, externals, media = get_course_content(page, course_id)

    # 3. Prepare Downloader
    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})
    session.cookies.update(get_requests_cookies())

    # 4. Download Standard Files
    print(f"[*] Downloading {len(files)} Canvas files...")
    for url in files:
        download_resource(url, course_dir, session)

    # 5. Process Media (Split into Download vs External)
    print(f"[*] Processing {len(media)} media items...")
    for url in media:
        # ONLY download if it looks like a file (mp4, etc)
        if is_direct_media_file(url):
            download_resource(url, course_dir, session)
        else:
            # Otherwise (YouTube, Vimeo, Streaming m3u8), save link to text file
            print(f"      [Log] Saving Media Link: {url}")
            externals.append(url)

    # 6. Save External Links
    print("[*] Saving External Links list...")
    # Deduplicate before saving
    unique_externals = sorted(list(set(externals)))
    with open(os.path.join(course_dir, "external_links.txt"), "w", encoding='utf-8') as f:
        for link in unique_externals:
            f.write(link + "\n")

    print(f"=== Completed {course_name} ===")

def main():
    if 'PASTE_HERE' in COOKIES[0]['value']:
        print("Error: Please update the COOKIES list.")
        return

    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        context.add_cookies(COOKIES)
        page = context.new_page()

        # 1. List Courses
        print("--- Finding Courses ---")
        try:
            page.goto(f"{BASE_URL}/courses", wait_until='networkidle')
            course_data = page.evaluate("""() => {
                const courses = [];
                document.querySelectorAll('a[href*="/courses/"]').forEach(a => {
                    const href = a.href;
                    const name = a.innerText.trim();
                    if (href && name) courses.push({href, name});
                });
                return courses;
            }""")

            courses_to_scrape = {}
            for item in course_data:
                parts = urlparse(item['href']).path.strip('/').split('/')
                if 'courses' in parts:
                    idx = parts.index('courses')
                    if idx + 1 < len(parts) and parts[idx+1].isdigit():
                        c_id = parts[idx+1]
                        c_name = item['name']
                        if "All Courses" not in c_name and c_id not in courses_to_scrape:
                            courses_to_scrape[c_id] = c_name

            print(f"Found {len(courses_to_scrape)} courses.")
        except Exception as e:
            print(f"Error finding courses: {e}")
            return

        # 2. Run
        for cid, cname in courses_to_scrape.items():
            process_course(page, cid, cname)

        browser.close()

if __name__ == "__main__":
    main()
