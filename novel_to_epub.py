import re
import requests
import os
import time
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from ebooklib import epub
import streamlit as st


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name)


def clean_text(text: str) -> str:
    # Trim spaces and collapse multiple blank lines
    text = re.sub(r'[ \t]+$', '', text, flags=re.M)
    text = re.sub(r'^\s+', '', text, flags=re.M)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def translate_in_chunks(chinese: str, translator) -> str:
    """
    Split long text into sub-5000-char chunks by paragraphs, translate each,
    then reassemble.
    """
    paras = chinese.split('\n\n')
    translated_parts = []
    buffer = ''
    for p in paras:
        piece = p.strip()
        if not piece:
            continue
        # +2 for the two newlines when we join
        if len(buffer) + len(piece) + 2 <= 4800:
            buffer = buffer + '\n\n' + piece if buffer else piece
        else:
            # translate buffer
            try:
                translated_parts.append(translator.translate(buffer))
            except Exception:
                translated_parts.append(buffer)
            buffer = piece
    # last buffer
    if buffer:
        try:
            translated_parts.append(translator.translate(buffer))
        except Exception:
            translated_parts.append(buffer)
    return '\n\n'.join(translated_parts)


def scrape_and_build_epub(base_url: str, start_page: int):
    # temp storage
    os.makedirs('temp_output', exist_ok=True)
    translator = GoogleTranslator(source='auto', target='en')
    novel_title = None
    txt_path = None
    page = start_page

    while True:
        url = f"{base_url}_{page}.html"
        try:
            r = requests.head(url, headers={'User-Agent': 'Mozilla/5.0'})
        except requests.RequestException:
            break
        if r.status_code == 404:
            break

        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(resp.text, 'html.parser')

        # get title once
        if novel_title is None:
            tag = soup.find(class_='article-title')
            novel_title = tag.get_text(strip=True) if tag else base_url.split('/')[-1]
            fname = sanitize_filename(novel_title) + '.txt'
            txt_path = os.path.join('temp_output', fname)
            with open(txt_path, 'w', encoding='utf-8'):
                pass

        # extract paragraphs
        content_div = soup.find(class_='article-content')
        if content_div:
            paras = [p.get_text(strip=True) for p in content_div.find_all('p') if p.get_text(strip=True)]
            if not paras:
                raw = content_div.get_text(separator='\n')
                paras = clean_text(raw).split('\n\n')
            full_chinese = '\n\n'.join(paras)
            # translate
            english = translate_in_chunks(full_chinese, translator)
            # append
            with open(txt_path, 'a', encoding='utf-8') as f:
                f.write(english + '\n\n')

        page += 1
        time.sleep(0.3)

    # build EPUB
    book = epub.EpubBook()
    book.set_identifier('id1')
    book.set_title(novel_title)
    book.set_language('en')

    # read the full text
    with open(txt_path, 'r', encoding='utf-8') as f:
        full_text = f.read()

    paras = [p for p in full_text.split('\n\n') if p.strip()]
    html_body = ''.join(f'<p>{p}</p>' for p in paras)

    c = epub.EpubHtml(title=novel_title, file_name='content.xhtml', lang='en')
    c.content = html_body
    book.add_item(c)
    book.toc = (c,)
    book.spine = ['nav', c]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub_path = txt_path.replace('.txt', '.epub')
    epub.write_epub(epub_path, book)
    return epub_path, novel_title


st.title("Webnovel ePub Downloader")
link = st.text_input("First chapter URL (…_2.html):")
if st.button("Download ePub"):
    if not link:
        st.error("Enter a valid URL ending in _n.html.")
    else:
        m = re.match(r"(.+)_([0-9]+)\.html", link)
        if not m:
            st.error("URL must end with _<number>.html")
        else:
            base, num = m.group(1), int(m.group(2))
            with st.spinner("Working… this may take some minutes"):
                epub_file, title = scrape_and_build_epub(base, start_page=num)
            with open(epub_file, 'rb') as ef:
                data = ef.read()
            st.success(f"Done: {title}")
            st.download_button("Download ePub", data=data, file_name=os.path.basename(epub_file), mime="application/epub+zip")
