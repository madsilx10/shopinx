"""
ShopinX Guaranteed MEXC Airdrop Bot Automation
Pakai Pyrogram (user bot via session string)

Format file input:
  akun.txt     → authtoken\nct0\nauthtoken\nct0\n...  (pasangan per akun)
  usn.txt      → usn1\nusn2\n...  (X/Twitter username, 1 per baris, tanpa @)
  sessions.txt → sessionstring1\nsessionstring2\n...  (Pyrogram session string, 1 per baris)

Urutan: sessions baris ke-N = usn baris ke-N = akun pasangan ke-N
"""

import asyncio
import re
import random
import time
from pathlib import Path

import requests
from pyrogram import Client
from pyrogram.errors import (
    FloodWait, UserAlreadyParticipant, UserBannedInChannel, InviteRequestSent
)

# ─────────────────────────────────────────────────────────────
# KONFIGURASI
# ─────────────────────────────────────────────────────────────
API_ID   = 12345678        # ← ganti
API_HASH = "your_api_hash" # ← ganti

BOT_USERNAME   = "ShopinxGuaranteedMEXCAirdropBot"
REFERRAL_START = "2005545171"

GROUP_CHAT   = "shopinxchat"
CHANNEL_CHAT = "ShopinXGeneral"
X_FOLLOW_TARGET = "shopinxSHOPINX"

DELAY_MIN = 3
DELAY_MAX = 7
ACCOUNT_DELAY_MIN = 10
ACCOUNT_DELAY_MAX = 25

X_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LW81lkxEzFu5oiZxOuF9A7GQ2TZJGQ63lmGDEWc"
)

# ─────────────────────────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────────────────────────
def rdelay(mn=DELAY_MIN, mx=DELAY_MAX):
    return asyncio.sleep(random.uniform(mn, mx))

def log(idx, msg, level="INFO"):
    print(f"[Akun #{idx+1}] [{level}] {msg}")

def load_lines(path):
    return [l.strip() for l in Path(path).read_text().splitlines() if l.strip()]

def load_akun(path="akun.txt"):
    lines = load_lines(path)
    return [
        {"authtoken": lines[i], "ct0": lines[i+1]}
        for i in range(0, len(lines) - 1, 2)
    ]

def solve_math(text):
    m = re.search(r'(\d+)\s*([+\-×x\*÷/])\s*(\d+)', text)
    if not m:
        return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    if op == '+':            return str(a + b)
    if op == '-':            return str(a - b)
    if op in ('×', 'x', '*'): return str(a * b)
    if op in ('÷', '/') and b: return str(a // b)
    return None

# ─────────────────────────────────────────────────────────────
# FOLLOW X (sync requests, skip jika sudah follow)
# ─────────────────────────────────────────────────────────────
def follow_x(cookies: dict, target: str, idx: int):
    headers = {
        "authorization": f"Bearer {X_BEARER}",
        "x-csrf-token": cookies["ct0"],
        "cookie": f"auth_token={cookies['authtoken']}; ct0={cookies['ct0']}",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
    }

    # 1. Lookup user_id pakai v1.1 users/show (lebih stabil dari GraphQL)
    try:
        r = requests.get(
            "https://api.twitter.com/1.1/users/show.json",
            headers={**headers, "content-type": "application/json"},
            params={"screen_name": target},
            timeout=15,
        )
        data = r.json()
        if "id_str" not in data:
            log(idx, f"❌ Lookup gagal, response: {str(data)[:150]}", "ERROR")
            return False
        user_id = data["id_str"]
        log(idx, f"🔍 User ID @{target}: {user_id}")
    except Exception as e:
        log(idx, f"❌ Gagal lookup @{target}: {e}", "ERROR")
        return False

    # 2. Cek sudah follow belum — skip jika iya
    try:
        r = requests.get(
            "https://api.twitter.com/1.1/friendships/show.json",
            headers={**headers, "content-type": "application/x-www-form-urlencoded"},
            params={"target_id": user_id},
            timeout=15,
        )
        if r.json().get("relationship", {}).get("source", {}).get("following"):
            log(idx, f"ℹ️  Sudah follow @{target}, skip")
            return True
    except Exception as e:
        log(idx, f"⚠️  Gagal cek friendship, lanjut follow: {e}", "WARN")

    # 3. Follow
    try:
        r = requests.post(
            "https://api.twitter.com/1.1/friendships/create.json",
            headers={**headers, "content-type": "application/x-www-form-urlencoded"},
            data=f"user_id={user_id}&include_entities=false&skip_status=true",
            timeout=15,
        )
        if r.status_code == 200:
            log(idx, f"✅ Follow @{target} sukses")
            return True
        log(idx, f"❌ Follow gagal ({r.status_code}): {r.text[:100]}", "ERROR")
        return False
    except Exception as e:
        log(idx, f"❌ Exception follow: {e}", "ERROR")
        return False

# ─────────────────────────────────────────────────────────────
# TELEGRAM HELPERS
# ─────────────────────────────────────────────────────────────
async def join_chat(client, chat, idx):
    try:
        await client.join_chat(chat)
        log(idx, f"✅ Join @{chat}")
        return True
    except UserAlreadyParticipant:
        log(idx, f"ℹ️  Sudah join @{chat}")
        return True
    except FloodWait as e:
        log(idx, f"⏳ FloodWait {e.value}s, tunggu...", "WARN")
        await asyncio.sleep(e.value + 2)
        return await join_chat(client, chat, idx)
    except Exception as e:
        log(idx, f"❌ Gagal join @{chat}: {e}", "ERROR")
        return False

async def click_btn(client, chat_id, msg, keywords, idx):
    if not msg or not msg.reply_markup:
        return False
    for row in msg.reply_markup.inline_keyboard:
        for btn in row:
            if any(kw.lower() in btn.text.lower() for kw in keywords):
                log(idx, f"🖱️  Klik: '{btn.text}'")
                try:
                    await client.request_callback_answer(
                        chat_id=chat_id,
                        message_id=msg.id,
                        callback_data=btn.callback_data,
                    )
                    return True
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                    return await click_btn(client, chat_id, msg, keywords, idx)
                except Exception as e:
                    log(idx, f"⚠️  Callback error: {e}", "WARN")
                    return False
    return False

async def wait_reply(client, bot_id, after_ts, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(1.5)
        async for m in client.get_chat_history(bot_id, limit=5):
            if m.date and m.date.timestamp() >= after_ts - 1:
                return m
    return None

# ─────────────────────────────────────────────────────────────
# FLOW UTAMA
# ─────────────────────────────────────────────────────────────
async def run_account(session_str, x_username, x_cookies, idx):
    client = Client(
        name=f"sess_{idx}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_str,
        in_memory=True,
    )

    async with client:
        me = await client.get_me()
        log(idx, f"Login: @{me.username or me.first_name}")

        bot = await client.get_chat(BOT_USERNAME)
        bot_id = bot.id

        # ── STEP 1: /start dengan referral ──────────────────────────
        log(idx, "▶ STEP 1: /start referral")
        now = time.time()
        await client.send_message(bot_id, f"/start {REFERRAL_START}")
        await rdelay(3, 5)
        msg = await wait_reply(client, bot_id, now)
        if not msg:
            log(idx, "❌ Bot tidak membalas", "ERROR")
            return False

        # ── STEP 2: Baca soal captcha dari pesan, klik Continue ─────
        # Soal math sudah ada di pesan ini bersama tombol Continue
        log(idx, "▶ STEP 2: Baca soal captcha + klik Continue")
        captcha_ans = solve_math(msg.text or "")
        if captcha_ans:
            log(idx, f"🧮 Soal terdeteksi → jawaban: {captcha_ans}")
        else:
            log(idx, "⚠️  Soal captcha tidak terdeteksi di pesan ini", "WARN")

        await click_btn(client, bot_id, msg, ["continue", "start", "next", "mulai"], idx)
        await rdelay(2, 4)

        # ── STEP 3: Bot balas "great..." → kirim jawaban captcha ────
        log(idx, "▶ STEP 3: Tunggu balas bot, kirim jawaban captcha")
        now = time.time()
        msg = await wait_reply(client, bot_id, now)

        if captcha_ans:
            now = time.time()
            await client.send_message(bot_id, captcha_ans)
            await rdelay(2, 4)
            msg = await wait_reply(client, bot_id, now)
        else:
            log(idx, "❌ Tidak ada jawaban captcha, skip step ini", "ERROR")

        # ── STEP 4: Follow @shopinxSHOPINX di X ────────────────────
        log(idx, f"▶ STEP 4: Follow @{X_FOLLOW_TARGET} di X")
        if x_cookies:
            follow_x(x_cookies, X_FOLLOW_TARGET, idx)
        else:
            log(idx, "⚠️  Tidak ada cookies X, skip follow", "WARN")
        await rdelay()

        # ── STEP 5: Join group & channel ────────────────────────────
        log(idx, f"▶ STEP 5: Join @{GROUP_CHAT} & @{CHANNEL_CHAT}")
        await join_chat(client, GROUP_CHAT, idx)
        await rdelay(2, 4)
        await join_chat(client, CHANNEL_CHAT, idx)
        await rdelay()

        # ── STEP 6: Ambil pesan terbaru bot, klik Done/Continue ─────
        # msg di sini masih pesan lama sebelum join — ambil yang terbaru dulu
        log(idx, "▶ STEP 6: Ambil pesan terbaru bot lalu klik Done")
        now = time.time()
        fresh_msg = None
        async for m in client.get_chat_history(bot_id, limit=1):
            fresh_msg = m
        if fresh_msg and fresh_msg.reply_markup:
            await click_btn(client, bot_id, fresh_msg, ["done", "continue", "verify", "check", "joined"], idx)
        else:
            log(idx, "⚠️  Tidak ada tombol di pesan terbaru, coba pakai msg lama", "WARN")
            await click_btn(client, bot_id, msg, ["done", "continue", "verify", "check", "joined"], idx)
        await rdelay(2, 4)
        msg = await wait_reply(client, bot_id, now)

        # ── STEP 7: Klik Done lagi ───────────────────────────────────
        log(idx, "▶ STEP 7: Klik Done (ke-2)")
        await click_btn(client, bot_id, msg, ["done", "confirm", "continue", "next"], idx)
        now = time.time()
        await rdelay()
        msg = await wait_reply(client, bot_id, now)

        # ── STEP 8: Submit X username ────────────────────────────────
        log(idx, f"▶ STEP 8: Submit X username → {x_username}")
        now = time.time()
        await client.send_message(bot_id, x_username.lstrip("@"))
        await rdelay(2, 4)
        msg = await wait_reply(client, bot_id, now)

        # ── STEP 9: Klik Done setelah X username ────────────────────
        log(idx, "▶ STEP 9: Klik Done setelah X username")
        await click_btn(client, bot_id, msg, ["done", "continue", "next", "submit"], idx)
        now = time.time()
        await rdelay()
        msg = await wait_reply(client, bot_id, now)

        # ── STEP 10: Submit wallet address ───────────────────────────
        log(idx, "▶ STEP 10: Submit wallet address")
        if msg and msg.text:
            if any(w in msg.text.lower() for w in ["wallet", "address", "bsc", "bnb", "eth"]):
                wallet = input(f"[Akun #{idx+1}] Wallet address: ").strip()
                now = time.time()
                await client.send_message(bot_id, wallet)
                await rdelay(2, 4)
                final = await wait_reply(client, bot_id, now)
                if final:
                    log(idx, f"📨 Respon akhir: {final.text[:200]}")
            else:
                log(idx, f"📨 Respon bot: {msg.text[:200]}")

        log(idx, "✅ Flow selesai!")
        return True

# ─────────────────────────────────────────────────────────────
# MENU INTERAKTIF
# ─────────────────────────────────────────────────────────────
def print_menu(total):
    print("\n" + "="*45)
    print("  ShopinX Airdrop Bot Automation")
    print("="*45)
    print(f"  Total akun: {total}")
    print("-"*45)
    print("  [1] 1 akun (pilih index)")
    print("  [2] Semua akun")
    print("  [3] Dari akun X sampai akhir")
    print("  [0] Keluar")
    print("="*45)

async def main():
    sessions  = load_lines("sessions.txt")
    usernames = load_lines("usn.txt")
    akun_list = load_akun("akun.txt") if Path("akun.txt").exists() else []

    if not sessions:
        print("❌ sessions.txt kosong!"); return
    if not usernames:
        print("❌ usn.txt kosong!"); return
    if len(sessions) != len(usernames):
        print(f"⚠️  Jumlah session ({len(sessions)}) ≠ username ({len(usernames)}), pakai terkecil")

    total = min(len(sessions), len(usernames))
    print_menu(total)
    choice = input("\nPilihan [0-3]: ").strip()

    if choice == "0":
        print("Keluar."); return
    elif choice == "1":
        try:
            idx = int(input(f"Nomor akun (1-{total}): ")) - 1
            assert 0 <= idx < total
        except:
            print("❌ Input tidak valid."); return
        run_range = [idx]
    elif choice == "2":
        run_range = list(range(total))
    elif choice == "3":
        try:
            start = int(input(f"Mulai dari akun ke- (1-{total}): ")) - 1
            assert 0 <= start < total
        except:
            print("❌ Input tidak valid."); return
        run_range = list(range(start, total))
    else:
        print("❌ Pilihan tidak dikenali."); return

    print(f"\n▶ Jalankan {len(run_range)} akun: {[i+1 for i in run_range]}\n")

    results = {}
    for i, idx in enumerate(run_range):
        log(idx, f"━━━ Mulai [{i+1}/{len(run_range)}] ━━━")
        try:
            cookies = akun_list[idx] if idx < len(akun_list) else None
            ok = await run_account(sessions[idx], usernames[idx], cookies, idx)
            results[idx] = "✅ Sukses" if ok else "⚠️ Selesai dengan peringatan"
        except FloodWait as e:
            log(idx, f"FloodWait {e.value}s", "WARN")
            await asyncio.sleep(e.value + 5)
            results[idx] = "⏳ FloodWait, skip"
        except Exception as e:
            log(idx, f"Exception: {e}", "ERROR")
            results[idx] = f"❌ Error: {e}"

        if i < len(run_range) - 1:
            jeda = random.uniform(ACCOUNT_DELAY_MIN, ACCOUNT_DELAY_MAX)
            log(idx, f"⏳ Jeda {jeda:.1f}s...")
            await asyncio.sleep(jeda)

    print("\n" + "="*45)
    print("  RINGKASAN")
    print("="*45)
    for idx, status in results.items():
        print(f"  Akun #{idx+1} (@{usernames[idx]}): {status}")
    print("="*45)

if __name__ == "__main__":
    asyncio.run(main())
