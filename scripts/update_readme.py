#!/usr/bin/env python3
"""Update README.md with latest blog posts and Telegram channel messages."""

import re
import os
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from urllib.error import URLError
from html.parser import HTMLParser

README_PATH = os.path.join(os.path.dirname(__file__), '..', 'README.md')

POSTS_START = '<!-- POSTS_START -->'
POSTS_END = '<!-- POSTS_END -->'
CHANNEL_START = '<!-- CHANNEL_START -->'
CHANNEL_END = '<!-- CHANNEL_END -->'


def fetch_url(url, headers=None):
    req = Request(url, headers=headers or {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/120.0.0.0 Safari/537.36'
    })
    with urlopen(req, timeout=15) as resp:
        return resp.read().decode('utf-8', errors='replace')


def strip_html(text):
    """Remove HTML tags from text."""
    return re.sub(r'<[^>]+>', '', text)


def fetch_blog_posts(count=3):
    """Fetch latest blog posts from RSS/Atom feed."""
    print('Fetching blog posts from RSS...')
    try:
        xml_text = fetch_url('https://blog.ursb.me/feed.xml')
        root = ET.fromstring(xml_text)

        ns = {'atom': 'http://www.w3.org/2005/Atom'}

        # Support both Atom (<entry>) and RSS (<channel><item>) formats
        entries = (
            root.findall('atom:entry', ns)
            or root.findall('{http://www.w3.org/2005/Atom}entry')
            or root.findall('.//entry')
        )
        # RSS 2.0: items live under <channel>
        if not entries:
            entries = root.findall('.//item')

        posts = []
        for entry in entries[:count]:
            # Title — may be wrapped in CDATA (ET strips that automatically)
            title_el = (
                entry.find('atom:title', ns)
                or entry.find('{http://www.w3.org/2005/Atom}title')
                or entry.find('title')
            )
            title = (title_el.text or '').strip() if title_el is not None else 'Untitled'

            # Link: Atom uses <link href="..."/>, RSS uses <link> text or <guid>
            link_el = (
                entry.find('atom:link', ns)
                or entry.find('{http://www.w3.org/2005/Atom}link')
                or entry.find('link')
            )
            if link_el is not None:
                url = link_el.get('href') or (link_el.text or '').strip()
            else:
                url = ''
            # Fallback to <guid> for RSS feeds
            if not url:
                guid_el = entry.find('guid')
                url = (guid_el.text or '').strip() if guid_el is not None else ''

            # Date: Atom uses <published>/<updated>, RSS uses <pubDate>
            date_el = (
                entry.find('atom:published', ns)
                or entry.find('{http://www.w3.org/2005/Atom}published')
                or entry.find('atom:updated', ns)
                or entry.find('{http://www.w3.org/2005/Atom}updated')
                or entry.find('published')
                or entry.find('updated')
                or entry.find('pubDate')
            )
            date_str = ''
            if date_el is not None and date_el.text:
                raw = date_el.text.strip()
                # ISO date: YYYY-MM-DD...
                m = re.match(r'(\d{4})-(\d{2})', raw)
                if m:
                    date_str = f'{m.group(1)}.{m.group(2)}'
                else:
                    # RFC 2822: "Sun, 15 Feb 2026 ..."
                    m2 = re.search(r'(\d{1,2})\s+(\w{3})\s+(\d{4})', raw)
                    if m2:
                        import calendar
                        months = {v: f'{i+1:02d}' for i, v in enumerate(calendar.month_abbr) if v}
                        day, mon, year = m2.group(1), m2.group(2), m2.group(3)
                        mm = months.get(mon, '01')
                        date_str = f'{year}.{mm}'

            posts.append((title, url, date_str))

        print(f'  Found {len(posts)} posts.')
        return posts
    except Exception as e:
        print(f'  ERROR fetching blog posts: {e}')
        return []


def fetch_channel_messages(count=3):
    """Fetch latest messages from Telegram channel static preview."""
    print('Fetching Telegram channel messages...')
    try:
        html = fetch_url('https://t.me/s/airingchannel')

        msg_pattern = re.compile(
            r'data-post="([^"]+)".*?'
            r'tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>.*?'
            r'<time\s+datetime="([^"]*)"',
            re.DOTALL
        )

        matches = msg_pattern.findall(html)
        # Take the last `count` messages
        matches = matches[-count:]

        messages = []
        for post_id, raw_text, datetime_str in matches:
            # Clean up text
            text = strip_html(raw_text)
            text = text.strip()

            # Take first non-empty line
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            text = lines[0] if lines else ''

            # Cut at URLs
            text = re.split(r'https?://', text)[0].strip()

            # Truncate to ~45 chars
            if len(text) > 45:
                text = text[:45].rstrip() + '...'

            # Build link
            link = f'https://t.me/{post_id}'

            # Format date as MM.DD
            date_str = ''
            m = re.match(r'\d{4}-(\d{2})-(\d{2})', datetime_str)
            if m:
                date_str = f'{m.group(1)}.{m.group(2)}'

            if text:
                messages.append((text, link, date_str))

        print(f'  Found {len(messages)} messages.')
        return messages
    except Exception as e:
        print(f'  ERROR fetching channel messages: {e}')
        return []


def format_items(items):
    """Format list of (title, url, date) into markdown lines."""
    lines = []
    for title, url, date in items:
        lines.append(f'- [{title}]({url}) <sub>{date}</sub>')
    return '\n'.join(lines)


def replace_section(content, start_marker, end_marker, new_content):
    """Replace content between markers."""
    pattern = rf'({re.escape(start_marker)}\n)(.*?)(\n{re.escape(end_marker)})'
    replacement = rf'\g<1>{new_content}\g<3>'
    result = re.sub(pattern, replacement, content, flags=re.DOTALL)
    return result


def main():
    # Read README
    readme_path = os.path.abspath(README_PATH)
    print(f'Reading README from {readme_path}')
    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read()

    updated = False

    # Update blog posts
    posts = fetch_blog_posts(count=3)
    if posts:
        new_posts = format_items(posts)
        content = replace_section(content, POSTS_START, POSTS_END, new_posts)
        print('  Updated POSTS section.')
        updated = True
    else:
        print('  Skipping POSTS section update.')

    # Update channel messages
    messages = fetch_channel_messages(count=3)
    if messages:
        new_channel = format_items(messages)
        content = replace_section(content, CHANNEL_START, CHANNEL_END, new_channel)
        print('  Updated CHANNEL section.')
        updated = True
    else:
        print('  Skipping CHANNEL section update.')

    if updated:
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print('README.md updated successfully.')
    else:
        print('No updates were made.')


if __name__ == '__main__':
    main()
