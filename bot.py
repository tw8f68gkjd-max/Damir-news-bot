import os
import re
import html
import time
import uuid
import threading
import calendar
import xml.etree.ElementTree as ET
from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urljoin
import feedparser
import requests
from telegram import Update, ReplyKeyboardMarkup, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
GROQ_MODEL = 'openai/gpt-oss-20b'
GEMINI_MODEL = 'gemini-3.8-flash'
ARTICLES_PER_FEED = 8
FRESH_HOURS = 24
MAX_AI_ARTICLES = 36
AI_BATCH_SIZE = 12
MAX_NEWS_EVENTS = 15
MAX_REGION_EVENTS = 10
MAX_SPORT_EVENTS = 12
NEWS_FEEDS = [{'region': '🇰🇿 Казахстан', 'source': 'Kazinform', 'publisher': 'Kazinform', 'url': 'https://qazinform.com/rss/en.xml'}, {'region': '🇰🇿 Казахстан', 'source': 'The Astana Times', 'publisher': 'The Astana Times', 'url': 'https://astanatimes.com/feed/'}, {'region': '🇺🇸 США', 'source': 'NPR', 'publisher': 'NPR', 'url': 'https://feeds.npr.org/1003/rss.xml'}, {'region': '🇺🇸 США', 'source': 'BBC', 'publisher': 'BBC', 'url': 'https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml'}, {'region': '🇪🇺 Европа', 'source': 'Euronews', 'publisher': 'Euronews', 'url': 'https://www.euronews.com/rss?format=mrss&level=vertical&name=my-europe'}, {'region': '🇪🇺 Европа', 'source': 'BBC', 'publisher': 'BBC', 'url': 'https://feeds.bbci.co.uk/news/world/europe/rss.xml'}, {'region': '🇨🇳 Китай', 'source': 'China News Service', 'publisher': 'China News Service', 'url': 'https://www.chinanews.com.cn/rss/china.xml'}, {'region': '🇨🇳 Китай', 'source': 'BBC', 'publisher': 'BBC', 'url': 'https://feeds.bbci.co.uk/news/world/asia/china/rss.xml'}, {'region': '🇷🇺 Россия', 'source': 'Интерфакс', 'publisher': 'Интерфакс', 'url': 'https://www.interfax.ru/rss.asp'}, {'region': '🇷🇺 Россия', 'source': 'Meduza', 'publisher': 'Meduza', 'url': 'https://meduza.io/rss2/all'}, {'region': '🌍 Мир', 'source': 'Euronews', 'publisher': 'Euronews', 'url': 'https://www.euronews.com/rss?format=mrss&level=theme&name=news'}, {'region': '🌍 Мир', 'source': 'BBC', 'publisher': 'BBC', 'url': 'https://feeds.bbci.co.uk/news/world/rss.xml'}, {'region': '🤖 AI / технологии', 'source': 'TechCrunch', 'publisher': 'TechCrunch', 'url': 'https://techcrunch.com/category/artificial-intelligence/feed/'}, {'region': '🤖 AI / технологии', 'source': 'The Verge', 'publisher': 'The Verge', 'url': 'https://www.theverge.com/rss/index.xml'}, {'region': '🏆 Спорт', 'source': 'BBC Sport', 'publisher': 'BBC Sport', 'url': 'https://feeds.bbci.co.uk/sport/rss.xml'}, {'region': '🏆 Спорт', 'source': 'BBC Sport • Football', 'publisher': 'BBC Sport', 'url': 'https://feeds.bbci.co.uk/sport/football/rss.xml'}, {'region': '🏆 Спорт', 'source': 'The Guardian Sport', 'publisher': 'The Guardian', 'url': 'https://www.theguardian.com/sport/rss'}, {'region': '🏆 Спорт', 'source': 'The Guardian Football', 'publisher': 'The Guardian', 'url': 'https://www.theguardian.com/football/rss'}, {'region': '🏆 Спорт', 'source': 'CBS Sports', 'publisher': 'CBS Sports', 'url': 'https://www.cbssports.com/rss/headlines/'}, {'region': '🏆 Спорт', 'source': 'CBS Sports • Soccer', 'publisher': 'CBS Sports', 'url': 'https://www.cbssports.com/rss/headlines/soccer'}, {'region': '🏆 Спорт', 'source': 'CBS Sports • NBA', 'publisher': 'CBS Sports', 'url': 'https://www.cbssports.com/rss/headlines/nba'}, {'region': '🏆 Спорт', 'source': 'CBS Sports • Tennis', 'publisher': 'CBS Sports', 'url': 'https://www.cbssports.com/rss/headlines/tennis'}]
MAIN_MENU = ReplyKeyboardMarkup([['🔥 Главное', '⚡ Кратко'], ['📰 Все новости', '🏆 Спорт'], ['💰 Финансы'], ['🇰🇿 Казахстан', '🇺🇸 США'], ['🇪🇺 Европа', '🇨🇳 Китай'], ['🇷🇺 Россия', '🌍 Мир'], ['🤖 AI / технологии']], resize_keyboard=True)
SPORT_MENU = ReplyKeyboardMarkup([['🏆 Весь спорт'], ['⚽ Футбол', '🏎 F1'], ['🏀 Баскетбол', '🎾 Теннис'], ['⬅️ Главное меню']], resize_keyboard=True)
REGION_BUTTONS = {'🇰🇿 Казахстан', '🇺🇸 США', '🇪🇺 Европа', '🇨🇳 Китай', '🇷🇺 Россия', '🌍 Мир', '🤖 AI / технологии'}
COMMAND_TO_REGION = {'kz': '🇰🇿 Казахстан', 'usa': '🇺🇸 США', 'europe': '🇪🇺 Европа', 'china': '🇨🇳 Китай', 'russia': '🇷🇺 Россия', 'world': '🌍 Мир', 'ai': '🤖 AI / технологии'}
SPORT_FILTERS = {'⚽ Футбол': '⚽ Футбол', '🏎 F1': '🏎 F1', '🏀 Баскетбол': '🏀 Баскетбол', '🎾 Теннис': '🎾 Теннис'}
SPORT_COMMANDS = {'football': '⚽ Футбол', 'f1': '🏎 F1', 'basketball': '🏀 Баскетбол', 'tennis': '🎾 Теннис'}
REGION_CODE_TO_LABEL = {'KZ': '🇰🇿 Казахстан', 'US': '🇺🇸 США', 'EUROPE': '🇪🇺 Европа', 'CHINA': '🇨🇳 Китай', 'RUSSIA': '🇷🇺 Россия', 'WORLD': '🌍 Мир', 'AI': '🤖 AI / технологии', 'SPORT_FOOTBALL': '⚽ Футбол', 'SPORT_F1': '🏎 F1', 'SPORT_BASKETBALL': '🏀 Баскетбол', 'SPORT_TENNIS': '🎾 Теннис', 'SPORT_OTHER': '🏆 Другой спорт'}
SPORT_LABELS = {'⚽ Футбол', '🏎 F1', '🏀 Баскетбол', '🎾 Теннис', '🏆 Другой спорт'}
IMPACT_RANK = {'LOW': 1, 'MEDIUM': 2, 'HIGH': 3}
ALMATY_TZ = ZoneInfo('Asia/Almaty')
COMPLIMENTS = ['Зарина, у тебя редкое сочетание любопытства и умения доводить идеи до результата.', 'Зарина, ты умеешь замечать детали, которые другие легко пропускают.', 'Зарина, твоя настойчивость — тихая суперсила: если тебе что-то действительно нужно, ты докопаешься до работающего решения.', 'Зарина, у тебя есть талант превращать сырую идею в вещь, которой реально хочется пользоваться.', 'Зарина, у тебя отлично получается не соглашаться на «и так сойдёт» — и именно поэтому результат становится лучше.', 'Зарина, ты умеешь сочетать здравый смысл с фантазией — редкая и очень полезная смесь.', 'Зарина, у тебя хороший внутренний радар на то, что можно сделать удобнее, понятнее и интереснее.', 'Зарина, твоя требовательность к качеству — это уважение к собственному времени.', 'Зарина, у тебя есть вкус к хорошим идеям — и ещё более ценный навык быстро отсеивать плохие.', 'Зарина, ты умеешь задать именно тот вопрос, после которого всё начинает складываться.', 'Зарина, ты умеешь быстро переходить от «а что если?» к «так, давай сделаем».', 'Зарина, у тебя классный баланс между «хочу красиво» и «должно нормально работать».', 'Зарина, сегодня тебе полагается официальный комплимент: ты заметно интереснее среднестатистического понедельника 😄']
BAD_IMAGE_WORDS = ('logo', 'favicon', 'icon', 'avatar', 'sprite', 'badge', 'advert', '/ads/', 'placeholder', 'default-image', '1x1')

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is running')

    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get('PORT', 10000))
    HTTPServer(('0.0.0.0', port), HealthHandler).serve_forever()

def clean_text(text):
    if not text:
        return ''
    text = html.unescape(str(text))
    text = re.sub('<[^>]+>', ' ', text)
    return ' '.join(text.replace('\n', ' ').split())

def protected_terms(text):
    tokens = re.findall("\\b[A-Za-z0-9][A-Za-z0-9.+#&'_-]*\\b", text or '')
    result = []
    for token in tokens:
        special = any((ch.isupper() for ch in token[1:])) or any((ch.isdigit() for ch in token)) or (len(token) >= 2 and token.isupper())
        if special and token not in result:
            result.append(token)
    return result[:14]

def looks_russian(text):
    text = text or ''
    cyr = len(re.findall('[А-Яа-яЁё]', text))
    lat = len(re.findall('[A-Za-z]', text))
    if cyr == 0:
        return False
    return cyr >= max(4, lat * 0.35)

def normalize_image_url(url, base_url=''):
    if not url:
        return None
    url = html.unescape(str(url)).strip()
    if url.startswith('//'):
        url = 'https:' + url
    elif base_url:
        url = urljoin(base_url, url)
    if not url.startswith(('http://', 'https://')):
        return None
    if any((word in url.lower() for word in BAD_IMAGE_WORDS)):
        return None
    return url

def image_from_feed_entry(entry, article_url=''):
    candidates = []
    for item in entry.get('media_content', []) or []:
        if isinstance(item, dict):
            candidates.append(item.get('url'))
    for item in entry.get('media_thumbnail', []) or []:
        if isinstance(item, dict):
            candidates.append(item.get('url'))
    for item in entry.get('enclosures', []) or []:
        if isinstance(item, dict):
            media_type = (item.get('type') or '').lower()
            if media_type.startswith('image/'):
                candidates.append(item.get('href') or item.get('url'))
    for candidate in candidates:
        image_url = normalize_image_url(candidate, article_url)
        if image_url:
            return image_url
    return None

def image_from_article_page(article_url):
    if not article_url or not article_url.startswith(('http://', 'https://')):
        return None
    try:
        response = requests.get(article_url, headers={'User-Agent': 'Mozilla/5.0 NewsBot/1.0'}, timeout=10)
        response.raise_for_status()
        page = response.text[:600000]
        patterns = ['<meta[^>]+(?:property|name)=["\\\'](?:og:image|twitter:image|twitter:image:src)["\\\'][^>]+content=["\\\']([^"\\\']+)["\\\']', '<meta[^>]+content=["\\\']([^"\\\']+)["\\\'][^>]+(?:property|name)=["\\\'](?:og:image|twitter:image|twitter:image:src)["\\\']']
        for pattern in patterns:
            match = re.search(pattern, page, flags=re.IGNORECASE)
            if match:
                image_url = normalize_image_url(match.group(1), article_url)
                if image_url:
                    return image_url
    except Exception as error:
        print('Image page error:', repr(error))
    return None

def parse_entry_timestamp(entry):
    for key in ('published_parsed', 'updated_parsed', 'created_parsed'):
        parsed = entry.get(key)
        if parsed:
            try:
                return float(calendar.timegm(parsed))
            except Exception:
                pass
    for key in ('published', 'updated', 'created'):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(str(raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            pass
        try:
            dt = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            pass
    return None

def fetch_feed_articles(feed_info):
    result = []
    try:
        response = requests.get(feed_info['url'], headers={'User-Agent': 'Mozilla/5.0 NewsBot/1.0'}, timeout=15)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        now_ts = time.time()
        max_age = FRESH_HOURS * 3600
        for entry in feed.entries[:ARTICLES_PER_FEED]:
            title = clean_text(entry.get('title', ''))
            if not title:
                continue
            published_ts = parse_entry_timestamp(entry)
            if published_ts is None:
                continue
            age = now_ts - published_ts
            if age > max_age or age < -6 * 3600:
                continue
            description = clean_text(entry.get('summary', entry.get('description', '')))
            link = entry.get('link', '')
            result.append({'source_region': feed_info['region'], 'source': feed_info['source'], 'publisher': feed_info.get('publisher', feed_info['source']), 'title': title, 'description': description, 'link': link, 'published_ts': published_ts, 'image_url': image_from_feed_entry(entry, link), 'protected': protected_terms(title + ' ' + description)})
    except Exception as error:
        print(f"RSS error {feed_info['source']}:", repr(error))
    return result

def collect_articles(region_filter=None):
    feeds = [feed for feed in NEWS_FEEDS if not region_filter or feed['region'] == region_filter]
    if not feeds:
        return []
    articles = []
    with ThreadPoolExecutor(max_workers=min(10, len(feeds))) as executor:
        futures = [executor.submit(fetch_feed_articles, feed) for feed in feeds]
        for future in as_completed(futures):
            try:
                articles.extend(future.result())
            except Exception as error:
                print('RSS worker error:', repr(error))
    unique = []
    seen = set()
    for article in articles:
        key = article.get('link') or (article.get('publisher'), article.get('title'))
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)
    unique.sort(key=lambda x: x.get('published_ts', 0), reverse=True)
    return unique

def select_articles_for_ai(articles):
    by_publisher = defaultdict(list)
    for article in articles:
        by_publisher[article.get('publisher', article.get('source'))].append(article)
    for items in by_publisher.values():
        items.sort(key=lambda x: x.get('published_ts', 0), reverse=True)
    selected = []
    used = set()
    for round_index in range(3):
        for publisher in sorted(by_publisher):
            items = by_publisher[publisher]
            if round_index >= len(items):
                continue
            article = items[round_index]
            key = article.get('link') or id(article)
            if key in used:
                continue
            selected.append(article)
            used.add(key)
            if len(selected) >= MAX_AI_ARTICLES:
                selected.sort(key=lambda x: x.get('published_ts', 0), reverse=True)
                return selected
    for article in articles:
        key = article.get('link') or id(article)
        if key in used:
            continue
        selected.append(article)
        used.add(key)
        if len(selected) >= MAX_AI_ARTICLES:
            break
    selected.sort(key=lambda x: x.get('published_ts', 0), reverse=True)
    return selected

def call_groq(prompt):
    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        return None
    for attempt in range(2):
        try:
            response = requests.post('https://api.groq.com/openai/v1/chat/completions', headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}, json={'model': GROQ_MODEL, 'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0.1, 'max_completion_tokens': 6500, 'reasoning_effort': 'low', 'include_reasoning': False, 'stream': False}, timeout=80)
            if response.status_code == 200:
                text = response.json()['choices'][0]['message'].get('content', '').strip()
                if text:
                    print('AI provider: GROQ')
                    return text
            print('Groq error:', response.status_code, response.text[:500])
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(2 + attempt * 2)
                continue
            break
        except Exception as error:
            print('Groq exception:', repr(error))
            time.sleep(2 + attempt * 2)
    return None

def call_gemini(prompt):
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return None
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'
    for attempt in range(2):
        try:
            response = requests.post(url, headers={'Content-Type': 'application/json', 'x-goog-api-key': api_key}, json={'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 6500}}, timeout=90)
            if response.status_code == 200:
                candidates = response.json().get('candidates', [])
                if candidates:
                    parts = candidates[0].get('content', {}).get('parts', [])
                    text = '\n'.join((p.get('text', '') for p in parts if p.get('text'))).strip()
                    if text:
                        print('AI provider: GEMINI FALLBACK')
                        return text
            print('Gemini error:', response.status_code, response.text[:500])
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(2 + attempt * 2)
                continue
            break
        except Exception as error:
            print('Gemini exception:', repr(error))
            time.sleep(2 + attempt * 2)
    return None

def ask_ai(prompt):
    return call_groq(prompt) or call_gemini(prompt)

def make_analysis_prompt(articles):
    blocks = []
    for index, article in enumerate(articles):
        description = clean_text(article.get('description', ''))[:700]
        protected = ', '.join(article.get('protected', [])) or 'нет'
        blocks.append(f"NEWS_{index}\nSOURCE_BUCKET: {article['source_region']}\nSOURCE: {article['source']}\nPUBLISHER: {article['publisher']}\nTITLE: {article['title']}\nDESCRIPTION: {description}\nPROTECTED_TERMS: {protected}")
    return f'\nТы редактор русскоязычного новостного агрегатора.\n\nДля КАЖДОГО NEWS_ обязательно верни одну строку.\nПорядок статьи в RSS НЕ означает её важность.\n\nЗадачи:\n1. Переведи заголовок на естественный русский.\n2. Дай краткое описание на русском максимум в 1–2 предложениях.\n3. Используй только TITLE и DESCRIPTION. Ничего не выдумывай.\n4. Не заменяй человека, спортсмена, команду, бренд, компанию или продукт на другого.\n5. PROTECTED_TERMS сохраняй точно; если русская передача имени сомнительна — оставь латиницей.\n6. Выбери категорию:\n   KZ = Казахстан\n   US = США\n   EUROPE = Европа\n   CHINA = Китай\n   RUSSIA = Россия\n   AI = AI / технологии\n   SPORT_FOOTBALL = футбол\n   SPORT_F1 = Formula 1 / F1\n   SPORT_BASKETBALL = баскетбол / NBA\n   SPORT_TENNIS = теннис\n   SPORT_OTHER = другой спорт\n   WORLD = всё остальное\n7. Если главная суть — матч, турнир, спортсмен, команда, трансфер, гонка, рекорд,\n   травма спортсмена или спортивная организация — используй SPORT-категорию.\n8. Оцени значимость:\n   HIGH = крупное международное/национальное событие, финал, чемпионство, большой рекорд,\n          крупный трансфер, важное решение или событие большого масштаба.\n   MEDIUM = заметная новость более узкого масштаба.\n   LOW = рутинная, нишевая или малозначимая публикация.\n9. Не повышай важность из-за кликбейтного заголовка.\n10. Слухи, обвинения, заявления и прогнозы не выдавай за установленный факт.\n\nФормат каждой строки:\nNEWS_0|||HIGH|||SPORT_FOOTBALL|||РУССКИЙ ЗАГОЛОВОК|||КРАТКОЕ ОПИСАНИЕ\n\nНе используй Markdown. Не используй JSON. Не пиши ничего кроме строк NEWS_.\n\nПубликации:\n\n{chr(10).join(blocks)}\n'.strip()

def parse_analysis_response(raw_text, count):
    result = {}
    if not raw_text:
        return result
    for line in raw_text.splitlines():
        line = line.strip()
        if not line.startswith('NEWS_'):
            continue
        pieces = line.split('|||', 4)
        if len(pieces) != 5:
            continue
        try:
            index = int(pieces[0].replace('NEWS_', ''))
        except ValueError:
            continue
        if not 0 <= index < count:
            continue
        impact = pieces[1].strip().upper()
        code = pieces[2].strip().upper()
        title_ru = pieces[3].strip()
        summary_ru = pieces[4].strip()
        if impact not in IMPACT_RANK:
            impact = 'MEDIUM'
        result[index] = {'impact': impact, 'display_region': REGION_CODE_TO_LABEL.get(code, '🌍 Мир'), 'title_ru': title_ru, 'summary_ru': summary_ru}
    return result

def translate_single_article(article):
    prompt = f"\nПереведи новость на естественный русский язык.\nНичего не добавляй и не выдумывай.\nИмена людей, команд, компаний и брендов не заменяй на другие.\n\nTITLE: {article['title']}\nDESCRIPTION: {clean_text(article.get('description', ''))[:800]}\n\nВерни ровно две строки:\nTITLE|||русский заголовок\nSUMMARY|||краткое описание на русском максимум в 2 предложениях\n".strip()
    raw = ask_ai(prompt)
    if not raw:
        return None
    title_ru = ''
    summary_ru = ''
    for line in raw.splitlines():
        if line.startswith('TITLE|||'):
            title_ru = line.split('|||', 1)[1].strip()
        elif line.startswith('SUMMARY|||'):
            summary_ru = line.split('|||', 1)[1].strip()
    if title_ru and looks_russian(title_ru):
        return (title_ru, summary_ru)
    return None

def process_articles_with_ai(articles):
    processed = {}
    for batch_start in range(0, len(articles), AI_BATCH_SIZE):
        batch = articles[batch_start:batch_start + AI_BATCH_SIZE]
        raw = ask_ai(make_analysis_prompt(batch))
        parsed = parse_analysis_response(raw, len(batch))
        for local_index, item in parsed.items():
            global_index = batch_start + local_index
            processed[global_index] = item
    for index, article in enumerate(articles):
        item = processed.get(index)
        needs_translation = item is None or not item.get('title_ru') or (not looks_russian(item.get('title_ru', ''))) or (item.get('summary_ru') and (not looks_russian(item.get('summary_ru', ''))))
        if needs_translation:
            translated = translate_single_article(article)
            if translated:
                title_ru, summary_ru = translated
                if item is None:
                    item = {'impact': 'MEDIUM', 'display_region': article['source_region']}
                item['title_ru'] = title_ru
                item['summary_ru'] = summary_ru
                processed[index] = item
    return processed

def make_grouping_prompt(articles, processed):
    blocks = []
    for index, article in enumerate(articles):
        item = processed.get(index)
        if not item or not item.get('title_ru'):
            continue
        blocks.append(f"ITEM_{index}\nPUBLISHER: {article['publisher']}\nTITLE: {item['title_ru']}\nSUMMARY: {item.get('summary_ru', '')[:450]}")
    return f'\nТы объединяешь публикации разных СМИ в события.\n\nЕсли две публикации описывают ОДНО И ТО ЖЕ конкретное событие,\nдай им одинаковый GROUP_ID.\n\nНе объединяй:\n- разные матчи одной команды;\n- разные новости об одном человеке;\n- общую тему и отдельное событие;\n- слух и другое независимое событие.\n\nЕсли сомневаешься — оставляй отдельную группу.\n\nВерни по одной строке на каждый ITEM_:\nITEM_0|||GROUP_1\nITEM_1|||GROUP_2\n\nНикакого Markdown и пояснений.\n\n{chr(10).join(blocks)}\n'.strip()

def parse_grouping_response(raw_text, valid_indexes):
    result = {}
    if not raw_text:
        return result
    valid_indexes = set(valid_indexes)
    for line in raw_text.splitlines():
        line = line.strip()
        if not line.startswith('ITEM_'):
            continue
        pieces = line.split('|||', 1)
        if len(pieces) != 2:
            continue
        try:
            index = int(pieces[0].replace('ITEM_', ''))
        except ValueError:
            continue
        if index not in valid_indexes:
            continue
        group_id = pieces[1].strip()
        if group_id:
            result[index] = group_id
    return result

def add_event_groups(articles, processed):
    valid_indexes = [i for i in range(len(articles)) if i in processed and processed[i].get('title_ru')]
    if not valid_indexes:
        return processed
    raw = ask_ai(make_grouping_prompt(articles, processed))
    groups = parse_grouping_response(raw, valid_indexes)
    for index in valid_indexes:
        processed[index]['event_id'] = groups.get(index, f'UNIQUE_{index}')
    return processed

def group_articles(articles, processed):
    events = OrderedDict()
    for index, article in enumerate(articles):
        data = processed.get(index)
        if not data:
            continue
        title_ru = data.get('title_ru', '').strip()
        if not title_ru or not looks_russian(title_ru):
            continue
        event_id = data.get('event_id', f'UNIQUE_{index}')
        if event_id not in events:
            events[event_id] = {'region': data.get('display_region', article['source_region']), 'title': title_ru, 'summary': data.get('summary_ru', ''), 'impact': data.get('impact', 'MEDIUM'), 'published_ts': article.get('published_ts', 0), 'image_url': article.get('image_url'), 'sources': []}
        else:
            events[event_id]['published_ts'] = max(events[event_id].get('published_ts', 0), article.get('published_ts', 0))
            old_impact = events[event_id].get('impact', 'MEDIUM')
            new_impact = data.get('impact', 'MEDIUM')
            if IMPACT_RANK.get(new_impact, 0) > IMPACT_RANK.get(old_impact, 0):
                events[event_id]['impact'] = new_impact
            if not events[event_id].get('image_url') and article.get('image_url'):
                events[event_id]['image_url'] = article['image_url']
        events[event_id]['sources'].append({'name': article['source'], 'publisher': article.get('publisher', article['source']), 'link': article.get('link', '')})
    return list(events.values())

def unique_source_links(sources):
    result = []
    seen = set()
    for source in sources:
        key = (source.get('name', ''), source.get('link', ''))
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result

def unique_publishers(sources):
    result = []
    seen = set()
    for source in sources:
        publisher = source.get('publisher') or source.get('name') or 'Источник'
        if publisher in seen:
            continue
        seen.add(publisher)
        result.append(publisher)
    return result

def event_quality_key(event):
    publishers_count = len(unique_publishers(event.get('sources', [])))
    return (IMPACT_RANK.get(event.get('impact', 'MEDIUM'), 0), min(publishers_count, 5), event.get('published_ts', 0))

def rank_events(events):
    return sorted(events, key=event_quality_key, reverse=True)

def is_sport_event(event):
    return event.get('region') in SPORT_LABELS

def filter_events(events, region_filter=None, sport_filter=None):
    if sport_filter:
        return [e for e in events if e.get('region') == sport_filter]
    if region_filter == '🏆 Спорт':
        return [e for e in events if is_sport_event(e)]
    if region_filter:
        return [e for e in events if e.get('region') == region_filter]
    return events

def format_age(published_ts):
    if not published_ts:
        return None
    seconds = max(0, time.time() - published_ts)
    minutes = int(seconds // 60)
    if minutes < 1:
        return 'только что'
    if minutes < 60:
        return f'{minutes} мин назад'
    return f'{int(minutes // 60)} ч назад'

def save_event_card(application, event):
    card_id = uuid.uuid4().hex[:12]
    cards = application.bot_data.setdefault('event_cards', {})
    cards[card_id] = event
    while len(cards) > 300:
        cards.pop(next(iter(cards)), None)
    return card_id

def make_news_keyboard(card_id):
    return InlineKeyboardMarkup([[InlineKeyboardButton('📖 Подробнее', callback_data=f'd:{card_id}'), InlineKeyboardButton('💡 Почему важно?', callback_data=f'w:{card_id}')], [InlineKeyboardButton('🗞 Источники', callback_data=f's:{card_id}')]])

def make_event_text(event):
    sources = unique_source_links(event.get('sources', []))
    event['sources'] = sources
    publishers = unique_publishers(sources)
    age = format_age(event.get('published_ts'))
    message = f"{event['region']}\n\n📰 {event['title']}\n"
    if event.get('summary'):
        message += f"\nКоротко: {event['summary']}\n"
    if age:
        message += f'\n🕒 {age}'
    if publishers:
        message += f'\n🗞 Источников: {len(publishers)} — ' + ' • '.join(publishers)
    else:
        message += '\n🗞 Источников: 0'
    return message

def ensure_event_image(event):
    if event.get('image_url'):
        return event['image_url']
    for source in unique_source_links(event.get('sources', []))[:2]:
        image_url = image_from_article_page(source.get('link', ''))
        if image_url:
            event['image_url'] = image_url
            return image_url
    return None

async def send_events(update, context, events, with_images=False):
    for event in events:
        message = make_event_text(event)
        card_id = save_event_card(context.application, event)
        keyboard = make_news_keyboard(card_id)
        if with_images:
            image_url = ensure_event_image(event)
            if image_url:
                caption = message if len(message) <= 1000 else message[:997] + '...'
                try:
                    await update.message.reply_photo(photo=image_url, caption=caption, reply_markup=keyboard)
                    continue
                except Exception as error:
                    print('Telegram photo error:', repr(error))
        await update.message.reply_text(message, disable_web_page_preview=True, reply_markup=keyboard)

def make_details_prompt(event):
    publishers = ', '.join(unique_publishers(event.get('sources', [])))
    return f"Заголовок: {event['title']}\nОписание: {event.get('summary', '')}\nИсточники: {publishers}\n\nОбъясни подробнее на русском максимум в 5 коротких предложениях. Используй только данные карточки. Ничего не выдумывай. Сохраняй нейтральный тон. Если данных мало — скажи об этом."

def make_why_prompt(event):
    return f"Заголовок: {event['title']}\nОписание: {event.get('summary', '')}\n\nОбъясни нейтрально, почему событие может иметь значение. 2–4 коротких предложения. Не выдумывай факты и не драматизируй. Если последствия неизвестны — скажи об этом."

async def news_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        action, card_id = query.data.split(':', 1)
    except Exception:
        return
    event = context.application.bot_data.get('event_cards', {}).get(card_id)
    if not event:
        await query.message.reply_text('Эта карточка уже устарела 🙂\nЗапроси новости заново.')
        return
    if action == 's':
        buttons = []
        for source in unique_source_links(event.get('sources', [])):
            link = source.get('link', '')
            if link.startswith(('http://', 'https://')):
                buttons.append([InlineKeyboardButton('🔗 ' + source.get('name', 'Источник'), url=link)])
        if buttons:
            await query.message.reply_text('🗞 Открыть источники:', reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await query.message.reply_text('Для этой новости нет доступных ссылок.')
        return
    if action == 'd':
        cache_key = '_details'
        title = '📖 Подробнее'
        wait_text = '📖 Готовлю подробности...'
        prompt = make_details_prompt(event)
    else:
        cache_key = '_why'
        title = '💡 Почему это важно?'
        wait_text = '💡 Анализирую значение...'
        prompt = make_why_prompt(event)
    if event.get(cache_key):
        await query.message.reply_text(title + '\n\n' + event[cache_key])
        return
    wait_message = await query.message.reply_text(wait_text)
    answer = ask_ai(prompt)
    if not answer:
        await wait_message.edit_text('⚠️ AI сейчас временно не смог подготовить ответ.')
        return
    event[cache_key] = answer
    await wait_message.edit_text(title + '\n\n' + answer)

def xml_child_text(item, name):
    for child in list(item):
        if child.tag.split('}')[-1].lower() == name.lower():
            return (child.text or '').strip()
    return ''

def to_float(value):
    if value is None:
        return None
    match = re.search('-?\\d+(?:[.,]\\d+)?', str(value).replace(' ', ''))
    if not match:
        return None
    try:
        return float(match.group(0).replace(',', '.'))
    except ValueError:
        return None

def fetch_nbk_rates():
    response = requests.get('https://nationalbank.kz/rss/rates_all.xml', headers={'User-Agent': 'Mozilla/5.0 NewsBot/1.0'}, timeout=20)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    wanted = {'USD', 'EUR', 'GBP', 'CNY', 'RUB'}
    rates = {}
    for item in root.iter():
        if item.tag.split('}')[-1].lower() != 'item':
            continue
        code = xml_child_text(item, 'title').upper().strip()
        if code not in wanted:
            continue
        value = to_float(xml_child_text(item, 'description'))
        quantity = to_float(xml_child_text(item, 'quant')) or 1.0
        if value is None:
            continue
        rates[code] = value / max(quantity, 1.0)
    return rates

def fetch_coinbase_spot(pair):
    response = requests.get(f'https://api.coinbase.com/v2/prices/{pair}/spot', headers={'User-Agent': 'Mozilla/5.0 NewsBot/1.0'}, timeout=20)
    response.raise_for_status()
    return to_float(response.json().get('data', {}).get('amount'))

def format_usd_price(value):
    if value is None:
        return 'н/д'
    if value >= 1000:
        return f'${value:,.0f}'.replace(',', ' ')
    return f'${value:,.2f}'.replace(',', ' ')

async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = await update.message.reply_text('💰 Обновляю финансовые данные...')
    try:
        rates = fetch_nbk_rates()
    except Exception as error:
        print('NBK error:', repr(error))
        rates = {}
    try:
        btc = fetch_coinbase_spot('BTC-USD')
    except Exception:
        btc = None
    try:
        eth = fetch_coinbase_spot('ETH-USD')
    except Exception:
        eth = None
    lines = ['💰 Финансы', '', '💱 Официальный курс НБК']
    currencies = [('USD', '🇺🇸', 'доллар'), ('EUR', '🇪🇺', 'евро'), ('GBP', '🇬🇧', 'фунт стерлингов'), ('CNY', '🇨🇳', 'юань'), ('RUB', '🇷🇺', 'рубль')]
    if rates:
        for code, emoji, name in currencies:
            value = rates.get(code)
            if value is not None:
                lines.append(f'{emoji} 1 {code} ({name}) = {value:.2f} ₸')
    else:
        lines.append('Курсы сейчас недоступны')
    lines += ['', '🪙 Крипто', '₿ BTC/USD ≈ ' + format_usd_price(btc), '◆ ETH/USD ≈ ' + format_usd_price(eth), '', '🏦 Валюты — официальный курс Национального Банка Казахстана.', '🪙 Крипто — публичная spot-цена Coinbase.', 'ℹ️ Курс НБК — не курс покупки/продажи в банке или обменнике.']
    await message.edit_text('\n'.join(lines))

async def build_events(region_filter=None, sport_filter=None):
    source_region = '🏆 Спорт' if sport_filter else region_filter
    articles = collect_articles(source_region)
    if not articles:
        return ([], 'no_articles')
    ai_articles = select_articles_for_ai(articles)
    processed = process_articles_with_ai(ai_articles)
    usable = [i for i in range(len(ai_articles)) if i in processed and processed[i].get('title_ru') and looks_russian(processed[i].get('title_ru', ''))]
    if not usable:
        return ([], 'ai_failed')
    processed = add_event_groups(ai_articles, processed)
    events = group_articles(ai_articles, processed)
    events = filter_events(events, region_filter=region_filter, sport_filter=sport_filter)
    return (events, None)

async def run_news_request(update, context, region_filter=None, sport_filter=None, important_only=False):
    if important_only:
        status_text = '🔥 Ищу главное за последние 24 часа...\n🧠 Сравниваю значимость, источники и свежесть'
    elif sport_filter:
        status_text = f'🔎 Собираю {sport_filter} за последние {FRESH_HOURS} часов...'
    elif region_filter == '🏆 Спорт':
        status_text = '🏆 Собираю спорт...\n🧠 Выбираю значимые события, а не первые строки RSS'
    elif region_filter:
        status_text = f'🔎 Собираю свежие новости: {region_filter}'
    else:
        status_text = '🔎 Собираю свежие новости...\n🧠 Ранжирую по значимости, источникам и свежести'
    status = await update.message.reply_text(status_text)
    events, error = await build_events(region_filter=region_filter, sport_filter=sport_filter)
    if error == 'no_articles':
        await status.edit_text(f'❌ Не нашёл свежих публикаций с подтверждённым временем за последние {FRESH_HOURS} часов.')
        return
    if error == 'ai_failed':
        await status.edit_text('⚠️ AI сейчас не смог нормально обработать новости.\nЧтобы не показывать сырые английские заголовки, выдачу не формирую.')
        return
    if important_only:
        events = [e for e in events if e.get('impact') == 'HIGH']
        events = rank_events(events)[:5]
    else:
        events = rank_events(events)
        if sport_filter or region_filter == '🏆 Спорт':
            events = events[:MAX_SPORT_EVENTS]
        elif region_filter:
            events = events[:MAX_REGION_EVENTS]
        else:
            events = events[:MAX_NEWS_EVENTS]
    try:
        await status.delete()
    except Exception:
        pass
    if not events:
        await update.message.reply_text('Подходящих свежих событий сейчас нет.')
        return
    await send_events(update, context, events, with_images=important_only)

async def brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = await update.message.reply_text('⚡ Собираю короткую сводку за последние 24 часа...')
    events, error = await build_events()
    if error:
        await status.edit_text('⚠️ Сейчас не удалось качественно собрать сводку. Попробуй ещё раз чуть позже.')
        return
    events = rank_events(events)[:5]
    try:
        await status.delete()
    except Exception:
        pass
    lines = ['⚡ Коротко: 5 важных событий за последние 24 часа']
    for number, event in enumerate(events, 1):
        sources_count = len(unique_publishers(event.get('sources', [])))
        lines.append(f"{number}. {event['region']} {event['title']} · {sources_count} ист.")
    await update.message.reply_text('\n\n'.join(lines))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('👋 Привет!\n\nЯ собираю свежие новости из нескольких редакций, сравниваю публикации, перевожу их на русский и объединяю одинаковые события.\n\nВыбирай раздел 👇', reply_markup=MAIN_MENU)

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Выбирай раздел 👇', reply_markup=MAIN_MENU)

async def sport_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('🏆 Что смотрим?', reply_markup=SPORT_MENU)

async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_news_request(update, context)

async def important(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_news_request(update, context, important_only=True)

async def all_sport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_news_request(update, context, region_filter='🏆 Спорт')

async def region_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command = update.message.text.split()[0].split('@')[0].lstrip('/').lower()
    region = COMMAND_TO_REGION.get(command)
    if region:
        await run_news_request(update, context, region_filter=region)

async def sport_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command = update.message.text.split()[0].split('@')[0].lstrip('/').lower()
    sport_filter = SPORT_COMMANDS.get(command)
    if sport_filter:
        await run_news_request(update, context, sport_filter=sport_filter)

async def manutd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Муха лох.\nСлабый везде 🤣')

async def zarina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(ALMATY_TZ).date()
    compliment = COMPLIMENTS[today.toordinal() % len(COMPLIMENTS)]
    await update.message.reply_text('💗 Комплимент дня для Зарины\n\n' + compliment + '\n\n✨ Возвращайся завтра за новым 😄')

def test_groq_connection():
    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        return (False, 'нет ключа')
    try:
        response = requests.get('https://api.groq.com/openai/v1/models', headers={'Authorization': f'Bearer {api_key}'}, timeout=15)
        if response.status_code != 200:
            return (False, f'HTTP {response.status_code}')
        models = {item.get('id') for item in response.json().get('data', [])}
        if GROQ_MODEL in models:
            return (True, 'API и модель доступны')
        return (False, 'модель не найдена')
    except Exception:
        return (False, 'нет ответа')

def test_gemini_connection():
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return (False, 'нет ключа')
    try:
        response = requests.get('https://generativelanguage.googleapis.com/v1beta/models', headers={'x-goog-api-key': api_key}, timeout=15)
        if response.status_code != 200:
            return (False, f'HTTP {response.status_code}')
        models = {item.get('name', '').replace('models/', '') for item in response.json().get('models', [])}
        if GEMINI_MODEL in models:
            return (True, 'API и модель доступны')
        return (False, 'модель не найдена')
    except Exception:
        return (False, 'нет ответа')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = await update.message.reply_text('🔎 Проверяю AI-сервисы...')
    groq_ok, groq_info = test_groq_connection()
    gemini_ok, gemini_info = test_gemini_connection()
    await message.edit_text(f"🤖 Статус AI\n\nGroq: {('✅' if groq_ok else '❌')} {groq_info}\nGemini: {('✅' if gemini_ok else '❌')} {gemini_info}")

async def menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == '🔥 Главное':
        return await important(update, context)
    if text == '⚡ Кратко':
        return await brief(update, context)
    if text == '📰 Все новости':
        return await news(update, context)
    if text == '💰 Финансы':
        return await markets(update, context)
    if text == '🏆 Спорт':
        return await sport_menu(update, context)
    if text == '🏆 Весь спорт':
        return await all_sport(update, context)
    if text in SPORT_FILTERS:
        return await run_news_request(update, context, sport_filter=SPORT_FILTERS[text])
    if text == '⬅️ Главное меню':
        return await menu(update, context)
    if text in REGION_BUTTONS:
        return await run_news_request(update, context, region_filter=text)
    await update.message.reply_text('Выбери раздел кнопками ниже 👇', reply_markup=MAIN_MENU)

async def post_init(application: Application):
    await application.bot.set_my_commands([BotCommand('news', 'Все новости'), BotCommand('brief', '5 новостей коротко'), BotCommand('important', 'Главные события'), BotCommand('markets', 'Финансы'), BotCommand('sport', 'Весь спорт'), BotCommand('football', 'Футбол'), BotCommand('f1', 'Formula 1'), BotCommand('basketball', 'Баскетбол'), BotCommand('tennis', 'Теннис'), BotCommand('kz', 'Казахстан'), BotCommand('usa', 'США'), BotCommand('europe', 'Европа'), BotCommand('china', 'Китай'), BotCommand('russia', 'Россия'), BotCommand('world', 'Мир'), BotCommand('ai', 'AI и технологии'), BotCommand('menu', 'Показать меню'), BotCommand('status', 'Проверить AI')])

def main():
    threading.Thread(target=run_web_server, daemon=True).start()
    app = Application.builder().token(os.environ['TELEGRAM_BOT_TOKEN']).post_init(post_init).build()
    handlers = [('start', start), ('menu', menu), ('news', news), ('brief', brief), ('important', important), ('markets', markets), ('sport', all_sport), ('status', status), ('manutd', manutd), ('zarina', zarina)]
    for command, function in handlers:
        app.add_handler(CommandHandler(command, function))
    for command in COMMAND_TO_REGION:
        app.add_handler(CommandHandler(command, region_command))
    for command in SPORT_COMMANDS:
        app.add_handler(CommandHandler(command, sport_command))
    app.add_handler(CallbackQueryHandler(news_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_buttons))
    print('Telegram bot started')
    app.run_polling()
if __name__ == '__main__':
    main()
