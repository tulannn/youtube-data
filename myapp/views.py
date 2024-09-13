import logging
import os
import re
import time
from datetime import datetime, timedelta

import googleapiclient.discovery
import gspread
from bs4 import BeautifulSoup
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render, redirect
from google.oauth2.service_account import Credentials
from gspread_formatting import *
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Google Sheets API setup
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = settings.SERVICE_ACCOUNT_FILE

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)

# YouTube API setup
api_service_name = "youtube"
api_version = "v3"

def home(request):
    return render(request, 'myapp/home.html')

def settings_view(request):
    if request.method == 'POST':
        request.session['developer_key'] = request.POST.get('developer_key')
        request.session['spreadsheet_id'] = request.POST.get('spreadsheet_id')
        return redirect('home')
    developer_key = request.session.get('developer_key', settings.DEVELOPER_KEY)
    spreadsheet_id = request.session.get('spreadsheet_id', settings.SPREADSHEET_ID)
    return render(request, 'myapp/settings.html', {'developer_key': developer_key, 'spreadsheet_id': spreadsheet_id})

def process_link(request):
    if request.method == 'POST':
        link = request.POST.get('youtube_link')
        date_option = request.POST.get('date_option')
        date_input = request.POST.get('date_input')
        developer_key = request.session.get('developer_key', settings.DEVELOPER_KEY)
        spreadsheet_id = request.session.get('spreadsheet_id', settings.SPREADSHEET_ID)

        logging.debug(f"Developer Key: {developer_key}")
        logging.debug(f"Spreadsheet ID: {spreadsheet_id}")

        youtube = googleapiclient.discovery.build(api_service_name, api_version, developerKey=developer_key)
        
        if 'channel' in link or 'user' in link or 'c/' in link or '@' in link:
            process_channel_videos(link, youtube, spreadsheet_id, date_option, date_input)
        else:
            process_single_video(link, youtube, spreadsheet_id)
        return HttpResponse("Link işleme tamamlandı.")
    return redirect('home')

def get_page_source(url):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get(url)
    
    last_height = driver.execute_script("return document.documentElement.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.documentElement.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    
    page_source = driver.page_source
    driver.quit()
    return page_source

def get_video_links(page_source, video_type):
    soup = BeautifulSoup(page_source, 'html.parser')
    video_links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if video_type in href:
            full_url = 'https://www.youtube.com' + href.split('&')[0]  # Remove any URL parameters
            if full_url not in video_links:
                video_links.append(full_url)
    return video_links

def get_video_data(video_id, youtube):
    try:
        request = youtube.videos().list(
            part="snippet,statistics,contentDetails,liveStreamingDetails",
            id=video_id
        )
        response = request.execute()
        
        items = response['items'][0]
        title = items['snippet']['title']
        view_count = items['statistics'].get('viewCount', 0)
        like_count = items['statistics'].get('likeCount', 0)
        comment_count = items['statistics'].get('commentCount', 0)
        publish_date = items['snippet']['publishedAt']
        video_link = f"https://www.youtube.com/watch?v={video_id}"
        live_streaming_details = items.get('liveStreamingDetails', {})
        duration = items['contentDetails']['duration']
        
        if live_streaming_details:
            video_type = 'Live'
        elif 'shorts' in video_link or is_short(duration):
            video_type = 'Shorts'
        else:
            video_type = 'Video'

        return {
            'title': title,
            'views': view_count,
            'likes': like_count,
            'comments': comment_count,
            'upload_date': publish_date,
            'video_link': video_link,
            'video_type': video_type
        }
    except Exception as e:
        raise

def save_to_txt(video_links, filename):
    with open(filename, "a") as file:
        for url in video_links:
            file.write(url + "\n")

def process_links(video_links, since_date, filename, youtube):
    filtered_links = []
    for video_link in video_links:
        video_date = get_video_date(video_link, youtube)
        if video_date:
            if since_date is None or video_date >= since_date:
                filtered_links.append(video_link)
                save_to_txt([video_link], filename)
            else:
                logging.info(f"Tarih sonuna gelindi: {video_link} (Yayınlanma Tarihi: {video_date})")
                return filtered_links
        else:
            logging.warning(f"Video tarihi alınamadı: {video_link}")
    return filtered_links

def normalize_channel_url(url):
    if not url.startswith('https://'):
        url = 'https://' + url
    if not url.startswith('https://www.youtube.com/'):
        url = url.replace('https://', 'https://www.youtube.com/', 1)
    url = url.rstrip('/')
    url = re.sub(r'(/videos|/shorts|/streams)$', '', url)
    return url

def extract_channel_name(url):
    match = re.search(r'(?:https?://)?(?:www\.)?youtube\.com/(?:c/|channel/|user/|@)([^/]+)', url)
    if match:
        return match.group(1)
    else:
        return 'unknown_channel'

def create_directory(channel_name):
    base_dir = 'kanal'
    channel_dir = os.path.join(base_dir, channel_name)
    if not os.path.exists(channel_dir):
        os.makedirs(channel_dir)
    return channel_dir

def is_short(duration):
    pattern = re.compile(r'PT(\d+M)?(\d+S)')
    match = pattern.match(duration)
    if match:
        minutes = match.group(1)
        seconds = match.group(2)
        if not minutes and seconds and int(seconds[:-1]) <= 60:
            return True
    return False

def extract_video_id(url):
    regex = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})"
    match = re.search(regex, url)
    if match:
        return match.group(1)
    else:
        raise ValueError("Invalid YouTube URL")

def initialize_sheet(sheet):
    headers = ["Title", "Views", "Likes", "Comments", "Upload Date", "Upload Time"]
    sections = {
        'Shorts': 'A',
        'Live': 'I',
        'Video': 'Q'
    }

    colors = {
        'Shorts': Color(0.137, 0.623, 0.733),
        'Live': Color(0.71, 0.004, 0.004),
        'Video': Color(1.0, 0.623, 0.008)
    }

    header_colors = [
        Color(1.0, 0.9, 0.9),
        Color(0.9, 1.0, 0.9),
        Color(0.9, 0.9, 1.0),
        Color(1.0, 1.0, 0.9),
        Color(0.9, 1.0, 1.0),
        Color(1.0, 0.9, 1.0)
    ]

    requests = []

    for section, start_col in sections.items():
        section_name_col = chr(min(ord(start_col) + 6, ord('Z')))
        if ord(section_name_col) - ord('A') >= 26:
            continue

        requests.append({
            'updateCells': {
                'range': {
                    'sheetId': sheet.id,
                    'startRowIndex': 0,
                    'endRowIndex': 1,
                    'startColumnIndex': ord(section_name_col) - ord('A'),
                    'endColumnIndex': ord(section_name_col) - ord('A') + 1
                },
                'rows': [{
                    'values': [{
                        'userEnteredValue': {'stringValue': section},
                        'userEnteredFormat': {
                            'backgroundColor': {
                                'red': colors[section].red,
                                'green': colors[section].green,
                                'blue': colors[section].blue
                            },
                            'horizontalAlignment': 'CENTER',
                            'textFormat': {
                                'foregroundColor': {'red': 1, 'green': 1, 'blue': 1},
                                'fontSize': 14,
                                'bold': True
                            }
                        }
                    }]
                }],
                'fields': 'userEnteredValue,userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)'
            }
        })

        for i, header in enumerate(headers):
            if ord(start_col) - ord('A') + i >= 26:
                continue

            requests.append({
                'updateCells': {
                    'range': {
                        'sheetId': sheet.id,
                        'startRowIndex': 0,
                        'endRowIndex': 1,
                        'startColumnIndex': ord(start_col) - ord('A') + i,
                        'endColumnIndex': ord(start_col) - ord('A') + i + 1
                    },
                    'rows': [{
                        'values': [{
                            'userEnteredValue': {'stringValue': header},
                            'userEnteredFormat': {
                                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},
                                'horizontalAlignment': 'CENTER',
                                'textFormat': {
                                    'foregroundColor': {'red': 0, 'green': 0, 'blue': 0},
                                    'fontSize': 12,
                                    'bold': True
                                }
                            }
                        }]
                    }],
                    'fields': 'userEnteredValue,userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)'
                }
            })

        for i, color in enumerate(header_colors):
            col_letter = chr(ord(start_col) + i)
            if ord(col_letter) - ord('A') >= 26:
                continue

            requests.append({
                'repeatCell': {
                    'range': {
                        'sheetId': sheet.id,
                        'startRowIndex': 1,
                        'startColumnIndex': ord(col_letter) - ord('A'),
                        'endColumnIndex': ord(col_letter) - ord('A') + 1
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': {
                                'red': color.red,
                                'green': color.green,
                                'blue': color.blue
                            }
                        }
                    },
                    'fields': 'userEnteredFormat(backgroundColor)'
                }
            })

        if ord(section_name_col) - ord('A') < 26:
            requests.append({
                'mergeCells': {
                    'range': {
                        'sheetId': sheet.id,
                        'startRowIndex': 1,
                        'endRowIndex': sheet.row_count,
                        'startColumnIndex': ord(section_name_col) - ord('A'),
                        'endColumnIndex': ord(section_name_col) - ord('A') + 1
                    },
                    'mergeType': 'MERGE_ALL'
                }
            })

            requests.append({
                'repeatCell': {
                    'range': {
                        'sheetId': sheet.id,
                        'startRowIndex': 1,
                        'endRowIndex': sheet.row_count,
                        'startColumnIndex': ord(section_name_col) - ord('A'),
                        'endColumnIndex': ord(section_name_col) - ord('A') + 1
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': {
                                'red': colors[section].red,
                                'green': colors[section].green,
                                'blue': colors[section].blue
                            }
                        }
                    },
                    'fields': 'userEnteredFormat(backgroundColor)'
                }
            })

    requests.extend([
        {
            'updateDimensionProperties': {
                'range': {
                    'sheetId': sheet.id,
                    'dimension': 'COLUMNS',
                    'startIndex': ord(sections['Shorts']) - ord('A'),
                    'endIndex': ord(sections['Shorts']) - ord('A') + 1
                },
                'properties': {
                    'pixelSize': 200
                },
                'fields': 'pixelSize'
            }
        },
        {
            'updateDimensionProperties': {
                'range': {
                    'sheetId': sheet.id,
                    'dimension': 'COLUMNS',
                    'startIndex': ord(sections['Live']) - ord('A'),
                    'endIndex': ord(sections['Live']) - ord('A') + 1
                },
                'properties': {
                    'pixelSize': 200
                },
                'fields': 'pixelSize'
            }
        },
        {
            'updateDimensionProperties': {
                'range': {
                    'sheetId': sheet.id,
                    'dimension': 'COLUMNS',
                    'startIndex': ord(sections['Video']) - ord('A'),
                    'endIndex': ord(sections['Video']) - ord('A') + 1
                },
                'properties': {
                    'pixelSize': 200
                },
                'fields': 'pixelSize'
            }
        }
    ])

    sheet.spreadsheet.batch_update({'requests': requests})
    set_frozen(sheet, rows=1)

def check_existing_link(sheet, youtube_url):
    all_values = sheet.get_all_values()
    all_formulas = sheet.get_all_values(value_render_option='FORMULA')
    
    for row_number, (row_values, row_formulas) in enumerate(zip(all_values, all_formulas), start=1):
        for cell_value, cell_formula in zip(row_values, row_formulas):
            cell_value = str(cell_value)
            cell_formula = str(cell_formula)
            if youtube_url in cell_value or (cell_formula and youtube_url in cell_formula):
                return row_number
    return None

def find_last_filled_row(sheet, start_col, end_col):
    col_values = sheet.get_all_values()
    last_filled_row = 1
    for i, row in enumerate(col_values, start=1):
        if any(row[ord(start_col)-ord('A'):ord(end_col)-ord('A')+1]):
            last_filled_row = i
    return last_filled_row

def write_to_google_sheet(sheet, youtube_url, data):
    try:
        sections = {
            'Shorts': ('A', 'G'),
            'Live': ('I', 'O'),
            'Video': ('Q', 'W')
        }
        colors = {
            'Shorts': Color(0.137, 0.623, 0.733),
            'Live': Color(0.71, 0.004, 0.004),
            'Video': Color(1.0, 0.623, 0.008)
        }
        header_colors = [
            Color(1.0, 0.9, 0.9),
            Color(0.9, 1.0, 0.9),
            Color(0.9, 0.9, 1.0),
            Color(1.0, 1.0, 0.9),
            Color(0.9, 1.0, 1.0),
            Color(1.0, 0.9, 1.0)
        ]
        video_type = data.get('video_type', 'Video')
        if video_type not in sections:
            raise ValueError(f"Invalid video type: {video_type}")

        start_col, end_col = sections[video_type]
        section_name_col = chr(ord(start_col) + 6)

        row_number = check_existing_link(sheet, youtube_url)
        if row_number:
            logging.info(f"This link already exists in the sheet on row {row_number}.")
            return

        row_number = find_last_filled_row(sheet, start_col, end_col) + 1

        if row_number > sheet.row_count:
            sheet.add_rows(100)

        title = data["title"].replace('"', '""')
        upload_datetime = datetime.strptime(data['upload_date'], '%Y-%m-%dT%H:%M:%SZ')
        upload_date = upload_datetime.strftime('%Y-%m-%d')
        upload_time = upload_datetime.strftime('%H:%M:%S')
        new_row = [title, data['views'], data['likes'], data['comments'], upload_date, upload_time]

        cell_list = sheet.range(f'{start_col}{row_number}:{end_col}{row_number}')
        for cell, value in zip(cell_list, new_row):
            cell.value = value
        sheet.update_cells(cell_list)

        safe_youtube_url = youtube_url.replace(';', '')
        sheet.update_acell(f'{start_col}{row_number}', f'=HYPERLINK("{safe_youtube_url}"; "{title}")')

        title_col = start_col
        row_format = CellFormat(
            textFormat=TextFormat(bold=True),
            horizontalAlignment='LEFT' if title_col == start_col else 'CENTER',
            wrapStrategy='CLIP'
        )
        format_cell_range(sheet, f'{title_col}{row_number}:{end_col}{row_number}', row_format)

        for i, color in enumerate(header_colors):
            col_letter = chr(ord(start_col) + i)
            format_cell_range(sheet, f'{col_letter}2:{col_letter}{sheet.row_count}', CellFormat(
                backgroundColor=color
            ))

        format_cell_range(sheet, f'{section_name_col}2:{section_name_col}{sheet.row_count}', CellFormat(
            backgroundColor=colors[video_type]
        ))

    except gspread.exceptions.APIError as e:
        logging.error(f"Google Sheets API error: {e}")
        logging.error(f"API response: {e.response.text}")
    except Exception as e:
        logging.error(f"An error occurred (write_to_google_sheet): {e}")

def normalize_sheet_name(sheet_name):
    normalized_name = re.sub(r'[^a-zA-Z0-9]', '', sheet_name).lower()
    return f"Sheet{normalized_name}"

def update_sheet(video_url, sheet_name, youtube, spreadsheet_id):
    try:
        video_id = extract_video_id(video_url)
        video_data = get_video_data(video_id, youtube)  # İki argüman ile çağır

        try:
            logging.info(f"Opening sheet with ID: {spreadsheet_id}")
            sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            logging.info(f"Worksheet not found, creating new worksheet: {sheet_name}")
            sheet = client.open_by_key(spreadsheet_id).add_worksheet(title=sheet_name, rows="1000", cols="26")

        initialize_sheet(sheet)
        write_to_google_sheet(sheet, video_url, video_data)
        time.sleep(10)
    except gspread.exceptions.SpreadsheetNotFound:
        logging.error(f"Spreadsheet with ID {spreadsheet_id} not found.")
        raise
    except Exception as e:
        logging.error(f"Error updating sheet: {e}")
        raise

def process_channel_videos(link, youtube, spreadsheet_id, date_option, date_input):
    channel_url = normalize_channel_url(link)
    channel_name = extract_channel_name(channel_url)
    six_months_ago = datetime.now() - timedelta(days=180)

    if date_option == 'tüm':
        since_date = None
    elif date_option == 'varsayılan':
        since_date = six_months_ago
    elif date_option == 'seç':
        if date_input:
            since_date = datetime.strptime(date_input, '%Y-%m-%d')
        else:
            raise ValueError("Tarih seçilmedi.")
    else:
        since_date = six_months_ago

    channel_dir = create_directory(channel_name)
    updateProcessStatus("Kanaldan linkler toplanıyor...")
    process_videos(channel_url, since_date, channel_dir, 'normal_videos.txt', '/videos', youtube)
    process_videos(channel_url, since_date, channel_dir, 'shorts_videos.txt', '/shorts', youtube)
    process_videos(channel_url, since_date, channel_dir, 'live_videos.txt', '/streams', youtube)

    links_processed = 0
    start_time = time.time()
    total_links = sum(1 for file in ["normal_videos.txt", "shorts_videos.txt", "live_videos.txt"] if os.path.exists(os.path.join(channel_dir, file)))
    
    for file in ["normal_videos.txt", "shorts_videos.txt", "live_videos.txt"]:
        file_path = os.path.join(channel_dir, file)
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                for line in f:
                    updateProcessStatus(f"{links_processed+1}/{total_links} link işleniyor...")
                    update_sheet(line.strip(), channel_name, youtube, spreadsheet_id)
                    links_processed += 1
                    if links_processed >= 6:
                        elapsed_time = time.time() - start_time
                        if elapsed_time < 100:
                            time.sleep(100 - elapsed_time)
                        links_processed = 0
                        start_time = time.time()
    
    updateProcessStatus("İşlem tamamlandı.")
    showCompleteButton()

def process_single_video(link, youtube, spreadsheet_id):
    updateProcessStatus("Video linki işleniyor...")
    update_sheet(link, "Sheet1", youtube, spreadsheet_id)
    updateProcessStatus("İşlem tamamlandı.")
    showCompleteButton()

def process_videos(channel_url, since_date, channel_dir, filename, video_type, youtube):
    page_source = get_page_source(f"{channel_url}{video_type}")
    video_links = get_video_links(page_source, '/watch?v=' if video_type != '/shorts' else '/shorts/')
    process_links(video_links, since_date, os.path.join(channel_dir, filename), youtube)

def get_video_date(video_link, youtube):
    try:
        video_id = extract_video_id(video_link)
        response = youtube.videos().list(part="snippet", id=video_id).execute()
        if "items" in response and len(response["items"]) > 0:
            publish_date = response["items"][0]["snippet"]["publishedAt"]
            return datetime.strptime(publish_date, '%Y-%m-%dT%H:%M:%SZ')
        else:
            return None
    except Exception as e:
        logging.error(f"An error occurred (get_video_date): {e}")
        return None

def updateProcessStatus(message):
    logging.info(message)

def showCompleteButton():
    logging.info("Tamam butonu gösteriliyor.")
