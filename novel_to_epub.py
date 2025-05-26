import requests
import re
import time
import os
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from ebooklib import epub


def sanitize_filename(name: str) -> str:
    """
    Replace forbidden filesystem characters in a title.
    """
    return re.sub(r'[\\/:*?"<>|]', '_', name)


def fetch_novel(base_url: str,
                start_page: int = 2,
                delay: float = 0.5,
                max_pages: int = None,
                output_dir: str = 'output') -> None:
    """
    Fetch translated chapters via headless Chrome, clean spacing,
    write to one .txt file (no chapter headers), then convert to EPUB.

    :param max_pages: stop after this many chapters if set; None fetches until 404.
    """
    os.makedirs(output_dir, exist_ok=True)
    page = start_page
    novel_title = None
    output_file = None
    end_page = start_page + max_pages - 1 if max_pages else None

    # Setup headless Chrome for auto-translation
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    prefs = {
        'translate_whitelists': {'zh-CN': 'en'},
        'translate': {'enabled': True}
    }
    chrome_options.add_experimental_option('prefs', prefs)
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    wait = WebDriverWait(driver, 10)

    while True:
        if end_page and page > end_page:
            print("Reached max_pages limit; stopping.")
            break

        url = f"{base_url}_{page}.html"
        # quick HEAD check for 404
        try:
            head = requests.head(url, headers={'User-Agent': 'Mozilla/5.0'})
        except Exception as e:
            print(f"HEAD request error: {e}")
            break
        if head.status_code == 404:
            print("404 reached; stopping.")
            break

        print(f"Loading {url}...")
        driver.get(url)
        # wait for translated content
        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'article-content')))
            time.sleep(1)
        except Exception:
            print(f"Missing content on chapter {page}; skipping.")
            page += 1
            time.sleep(delay)
            continue

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        if novel_title is None:
            tag = soup.find(class_='article-title')
            novel_title = tag.get_text(strip=True) if tag else base_url.split('/')[-1]
            fname = sanitize_filename(novel_title) + '.txt'
            output_file = os.path.join(output_dir, fname)
            print(f"Novel title: {novel_title}")
            print(f"Writing to: {output_file}")

        content_div = soup.find(class_='article-content')
        if not content_div:
            print(f"No content for chapter {page}; skipping.")
        else:
            paras = [p.get_text(strip=True) for p in content_div.find_all('p') if p.get_text(strip=True)]
            if paras:
                chapter_text = '\n\n'.join(paras)
            else:
                raw = content_div.get_text(separator='\n')
                raw = re.sub(r'[ \t]+$', '', raw, flags=re.M)
                raw = re.sub(r'^\s+', '', raw, flags=re.M)
                chapter_text = re.sub(r'\n{3,}', '\n\n', raw)

            with open(output_file, 'a', encoding='utf-8') as f:
                f.write(chapter_text)
                f.write('\n\n')
            print(f"Appended chapter {page}")

        page += 1
        time.sleep(delay)

    driver.quit()

    # Convert full .txt to single-chapter EPUB
    if output_file:
        book = epub.EpubBook()
        book.set_identifier('id1')
        book.set_title(novel_title)
        book.set_language('en')

        with open(output_file, 'r', encoding='utf-8') as f:
            full_text = f.read()

        paragraphs = [p for p in full_text.split('\n\n') if p.strip()]
        html_body = ''.join(f'<p>{p}</p>' for p in paragraphs)

        c = epub.EpubHtml(title=novel_title, file_name='content.xhtml', lang='en')
        c.content = html_body
        book.add_item(c)
        book.toc = (c,)
        book.spine = ['nav', c]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        epub_path = output_file.replace('.txt', '.epub')
        epub.write_epub(epub_path, book)
        print(f"EPUB created: {epub_path}")


if __name__ == '__main__':
    # pip install requests beautifulsoup4 selenium webdriver_manager ebooklib
    BASE_URL = 'https://www.52shuku.vip/yanqing/07_b/bjYyq'
    # Fetch the entire novel until 404:
    fetch_novel(BASE_URL, start_page=2)
