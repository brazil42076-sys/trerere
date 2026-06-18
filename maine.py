#!/usr/bin/env python3
"""
ULP FILE SEARCHER - TELEGRAM BOT
Search ULP files for domains and extract credentials
"""

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import re
import time
import threading
from datetime import datetime
from collections import defaultdict

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
bot = telebot.TeleBot(BOT_TOKEN)

# Store user sessions
user_sessions = {}

# ============================================================
# HELPERS
# ============================================================

def extract_domain(line):
    """Extract domain from URL line"""
    try:
        line = line.lower()
        if line.startswith('https://'):
            line = line[8:]
        elif line.startswith('http://'):
            line = line[7:]
        
        # Remove path
        slash = line.find('/')
        if slash != -1:
            line = line[:slash]
        
        # Remove port
        colon = line.find(':')
        if colon != -1 and line[colon+1:colon+2].isdigit():
            line = line[:colon]
        
        return line
    except:
        return None

def extract_path(line):
    """Extract path after domain"""
    try:
        if line.startswith('https://'):
            line = line[8:]
        elif line.startswith('http://'):
            line = line[7:]
        
        slash = line.find('/')
        if slash != -1:
            return line[slash+1:]
        return ''
    except:
        return ''

def parse_ulp_line(line):
    """Parse ULP format: https://domain.com/path:login:pass"""
    try:
        # Find the domain
        domain_match = re.search(r'https?://([^/:]+)', line)
        if domain_match:
            domain = domain_match.group(1)
        else:
            return None
        
        # Extract credentials
        parts = line.split(':')
        if len(parts) >= 3:
            # Format: https://domain.com/path:login:pass
            # The last two are login and pass
            login = parts[-2]
            password = parts[-1]
            return {
                'domain': domain,
                'url': line,
                'login': login,
                'password': password
            }
        return None
    except:
        return None

# ============================================================
# SEARCH ENGINE
# ============================================================

def search_ulp_file(file_path, queries, callback=None):
    """
    Search ULP file for domains
    """
    results = defaultdict(list)
    total_lines = 0
    
    # Convert queries to bytes for faster comparison
    query_bytes = [q.lower().encode('utf-8') for q in queries]
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            total_lines += 1
            line = line.strip()
            if not line:
                continue
            
            line_lower = line.lower()
            
            for q in queries:
                if q in line_lower:
                    parsed = parse_ulp_line(line)
                    if parsed:
                        results[q].append(parsed)
                    else:
                        # If can't parse, just store raw line
                        results[q].append({'raw': line})
            
            # Update progress
            if callback and total_lines % 10000 == 0:
                callback(total_lines)
    
    return results, total_lines

# ============================================================
# TELEGRAM BOT HANDLERS
# ============================================================

@bot.message_handler(commands=['start'])
def start_command(message):
    welcome_text = """🔍 *ULP FILE SEARCHER*

Send me a `.txt` ULP file then search for domains.

*Commands:*
/search `domain.com` - Search uploaded file
/stats - Show file info
/clear - Delete file and reset
/help - Show help

*File format:*
`https://domain.com/path:login:pass`"""

    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = """📖 *ULP SEARCHER HELP*

1. Send a `.txt` ULP file
2. Use `/search domain.com` to find matches
3. Results show URLs and credentials

*File format:*
`https://facebook.com/login:user:pass123`
`https://gmail.com:email:password`

*Commands:*
/search `<domain>` - Search for domain
/stats - Show file info
/clear - Delete file
/help - This message"""

    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(content_types=['document'])
def handle_file(message):
    chat_id = message.chat.id
    file_name = message.document.file_name
    
    if not file_name.endswith('.txt'):
        bot.reply_to(message, "❌ Only `.txt` files allowed")
        return
    
    status_msg = bot.reply_to(message, f"📥 Downloading `{file_name}`...", parse_mode='Markdown')
    
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        file_path = f"ulp_{chat_id}_{int(time.time())}.txt"
        with open(file_path, 'wb') as f:
            f.write(downloaded)
        
        # Count lines
        line_count = 0
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for _ in f:
                line_count += 1
        
        user_sessions[chat_id] = {
            'file_path': file_path,
            'file_name': file_name,
            'line_count': line_count
        }
        
        bot.edit_message_text(
            f"✅ File saved!\n\n📄 Name: `{file_name}`\n📊 Lines: `{line_count:,}`\n\nUse `/search domain.com` to find matches.",
            chat_id=chat_id,
            message_id=status_msg.message_id,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {str(e)[:100]}", chat_id=chat_id, message_id=status_msg.message_id)

@bot.message_handler(commands=['search'])
def search_command(message):
    chat_id = message.chat.id
    
    if chat_id not in user_sessions:
        bot.reply_to(message, "❌ Upload a `.txt` file first")
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: `/search domain.com`", parse_mode='Markdown')
        return
    
    query = parts[1].strip().lower()
    session = user_sessions[chat_id]
    file_path = session['file_path']
    
    if not os.path.exists(file_path):
        bot.reply_to(message, "❌ File not found. Upload again.")
        return
    
    status_msg = bot.reply_to(message, f"🔍 Searching for `{query}`...", parse_mode='Markdown')
    
    try:
        results = []
        total_lines = 0
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                total_lines += 1
                line = line.strip()
                if not line:
                    continue
                
                if query in line.lower():
                    parsed = parse_ulp_line(line)
                    if parsed:
                        results.append(parsed)
                    else:
                        results.append({'raw': line})
        
        if not results:
            bot.edit_message_text(
                f"❌ No matches found for `{query}`\n\n📊 Scanned: `{total_lines:,}` lines",
                chat_id=chat_id,
                message_id=status_msg.message_id,
                parse_mode='Markdown'
            )
            return
        
        # Save results to file
        result_file = f"results_{chat_id}_{query}_{int(time.time())}.txt"
        with open(result_file, 'w', encoding='utf-8') as f:
            f.write(f"# Search Results for: {query}\n")
            f.write(f"# Found: {len(results)} matches\n")
            f.write("#" + "="*60 + "\n\n")
            
            for r in results:
                if 'url' in r:
                    f.write(f"URL: {r['url']}\n")
                    f.write(f"Login: {r['login']}\n")
                    f.write(f"Pass: {r['password']}\n")
                    f.write("-"*40 + "\n")
                else:
                    f.write(f"{r['raw']}\n")
        
        bot.edit_message_text(
            f"✅ Found `{len(results)}` matches for `{query}`\n📊 Scanned: `{total_lines:,}` lines\n\n📁 Sending results...",
            chat_id=chat_id,
            message_id=status_msg.message_id,
            parse_mode='Markdown'
        )
        
        # Send results file
        with open(result_file, 'rb') as f:
            bot.send_document(
                chat_id,
                f,
                caption=f"🔍 Results for '{query}'\nFound: {len(results)} matches"
            )
        
        os.remove(result_file)
        
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {str(e)[:100]}", chat_id=chat_id, message_id=status_msg.message_id)

@bot.message_handler(commands=['stats'])
def stats_command(message):
    chat_id = message.chat.id
    
    if chat_id not in user_sessions:
        bot.reply_to(message, "❌ No file uploaded")
        return
    
    session = user_sessions[chat_id]
    file_path = session['file_path']
    
    if os.path.exists(file_path):
        size = os.path.getsize(file_path)
        bot.reply_to(message,
            f"📊 *File Stats*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📄 Name: `{session['file_name']}`\n"
            f"📊 Lines: `{session['line_count']:,}`\n"
            f"💾 Size: `{size / 1024:.2f} KB`\n\n"
            f"Use `/search domain.com` to search",
            parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ File not found. Upload again.")

@bot.message_handler(commands=['clear'])
def clear_command(message):
    chat_id = message.chat.id
    
    if chat_id in user_sessions:
        file_path = user_sessions[chat_id]['file_path']
        if os.path.exists(file_path):
            os.remove(file_path)
        del user_sessions[chat_id]
        bot.reply_to(message, "✅ File cleared. Upload a new one.")
    else:
        bot.reply_to(message, "❌ No active session.")

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("🤖 ULP Searcher Bot started...")
    bot.infinity_polling()