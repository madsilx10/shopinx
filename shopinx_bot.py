#!/usr/bin/env python3
"""
ShopinX Guaranteed MEXC Airdrop Bot Automation
Flow: /start reff → baca soal captcha + klik Continue → jawab captcha
      → join group → join channel → follow X
      → klik Done → klik Done lagi → submit usn X → klik Done → submit wallet

Format akun.txt    : authtoken\nct0\nauthtoken\nct0\n...  (tiap pasang pisah baris kosong opsional)
Format sessions.txt: satu session string per baris
Format usn.txt     : satu username X per baris (tanpa @)
Format wallet.txt  : satu wallet address per baris
"""

import asyncio
import random
import re
import sys
import os
import base64
import requests
from pyrogram import Client
from pyrogram.errors import UserAlreadyParticipant, FloodWait, InviteRequestSent

from config import (
    API_ID, API_HASH,
    BOT_USERNAME, REFF_CODE, TG_GROUP, TG_CHANNEL, X_FOLLOW_TARGET,
    COOLDOWN_MIN, COOLDOWN_MAX,
)

# ─── LOAD FILES ────────────────────────────────────────────────────────────────

def load_akun(path="akun.txt"):
    accounts = []
    with open(path) as f:
        lines = [l.strip() for l in f.read().strip().splitlines()]
    i = 0
    while i < len(lines):
        if lines[i] == "":
            i += 1
            continue
        auth_token = lines[i]
        ct0 = lines[i+1] if i+1 < len(lines) else ""
        accounts.append({"auth_token": auth_token, "ct0": ct0})
        i += 2
    return accounts

def load_lines(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [l.strip() for l in f if l.strip()]

# ─── X HELPERS ─────────────────────────────────────────────────────────────────

def gen_transaction_id():
    return base64.b64encode(os.urandom(75)).decode()

def x_headers(auth_token, ct0):
    return {
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "cookie": f"auth_token={auth_token}; ct0={ct0}",
        "x-csrf-token": ct0,
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en-US",
        "x-client-transaction-id": gen_transaction_id(),
        "origin": "https://x.com",
        "referer": "https://x.com/",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
    }

def x_get_user_id(auth_token, ct0, screen_name):
    try:
        r = requests.get(
            f"https://twitter.com/i/api/1.1/users/lookup.json?screen_name={screen_name}",
            headers=x_headers(auth_token, ct0),
            timeout=15
        )
        data = r.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0]["id_str"]
        print(f"  [!] Gagal ambil user ID {screen_name}: {data}")
        return None
    except Exception as e:
        print(f"  [!] Gagal ambil user ID {screen_name}: {e}")
        return None

def x_is_following(auth_token, ct0, target_screen_name):
    """Cek apakah sudah follow target. Return True jika sudah."""
    try:
        r = requests.get(
            "https://twitter.com/i/api/1.1/friendships/show.json",
            headers={**x_headers(auth_token, ct0), "content-type": "application/x-www-form-urlencoded"},
            params={"target_screen_name": target_screen_name},
            timeout=15
        )
        rel = r.json().get("relationship", {}).get("source", {})
        return bool(rel.get("following"))
    except Exception as e:
        print(f"  [!] Gagal cek friendship: {e}")
        return False

def x_follow(auth_token, ct0, target_user):
    # Cek dulu, skip jika sudah follow
    if x_is_following(auth_token, ct0, target_user):
        print(f"  [~] Sudah follow @{target_user}, skip")
        return True
    try:
        r = requests.post(
            "https://twitter.com/i/api/1.1/friendships/create.json",
            headers={**x_headers(auth_token, ct0), "content-type": "application/x-www-form-urlencoded"},
            data=f"screen_name={target_user}&skip_status=true",
            timeout=15
        )
        result = r.json()
        if "id" in result or result.get("following"):
            print(f"  [✓] Follow @{target_user}")
            return True
        print(f"  [!] Follow gagal: {result}")
        return False
    except Exception as e:
        print(f"  [!] Follow error: {e}")
        return False

# ─── TELEGRAM HELPERS ──────────────────────────────────────────────────────────

async def tg_join(client, target, label):
    try:
        await client.join_chat(target)
        print(f"  [✓] Join {label} @{target}")
        await asyncio.sleep(random.uniform(2, 4))
    except UserAlreadyParticipant:
        print(f"  [~] Sudah join {label} @{target}")
    except InviteRequestSent:
        print(f"  [~] Request join terkirim: @{target}")
    except FloodWait as e:
        print(f"  [!] FloodWait {e.value}s")
        await asyncio.sleep(e.value + 5)
        await tg_join(client, target, label)
    except Exception as e:
        print(f"  [!] Gagal join @{target}: {e}")

async def tunggu_pesan_bot(client, bot_id):
    await asyncio.sleep(random.uniform(2, 4))
    async for msg in client.get_chat_history(bot_id, limit=1):
        return msg
    return None

async def klik_button(client, bot_id, msg_id, keyword):
    try:
        msg = await client.get_messages(bot_id, msg_id)
        if not msg.reply_markup:
            print(f"  [!] Tidak ada button di pesan ini")
            return False
        for row in msg.reply_markup.inline_keyboard:
            for btn in row:
                if keyword.lower() in btn.text.lower():
                    await msg.click(btn.text)
                    print(f"  [✓] Klik: {btn.text}")
                    return True
        # fallback: klik tombol pertama
        first = msg.reply_markup.inline_keyboard[0][0]
        await msg.click(first.text)
        print(f"  [~] Fallback klik: {first.text}")
        return True
    except Exception as e:
        print(f"  [!] Klik button error: {e}")
        return False

def solve_captcha(text):
    match = re.search(r'(\d+)\s*([+\-*/x×÷])\s*(\d+)', text)
    if not match:
        return None
    a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
    if op == '+': return a + b
    if op == '-': return a - b
    if op in ('*', 'x', '×'): return a * b
    if op in ('/', '÷'): return a // b if b != 0 else 0
    return None

# ─── FLOW ──────────────────────────────────────────────────────────────────────

async def run_shopinx(session_string, auth_token, ct0, x_username, wallet, idx):
    print(f"\n{'='*55}")
    print(f"[Akun #{idx+1}] @{x_username} | {wallet[:10]}...")
    print(f"{'='*55}")

    client = Client(
        f"shopinx_{idx}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True
    )

    async with client:
        bot = await client.get_users(BOT_USERNAME)
        bot_id = bot.id

        # [1] Start bot dengan referral
        print(f"[1] Start bot...")
        await client.send_message(BOT_USERNAME, f"/start {REFF_CODE}")
        await asyncio.sleep(random.uniform(3, 5))

        # [2] Baca soal captcha dari pesan bot, lalu klik Continue
        print(f"[2] Baca soal captcha + klik Continue...")
        msg = await tunggu_pesan_bot(client, bot_id)
        jawaban = None
        if msg and msg.text:
            jawaban = solve_captcha(msg.text)
            if jawaban is not None:
                print(f"  [✓] Soal: {msg.text.strip()} → {jawaban}")
            else:
                print(f"  [!] Gagal parse soal: {msg.text!r}")
            await klik_button(client, bot_id, msg.id, "continue")
        await asyncio.sleep(random.uniform(2, 3))

        # [3] Bot balas "great..." → kirim jawaban captcha
        print(f"[3] Jawab captcha...")
        if jawaban is not None:
            await client.send_message(BOT_USERNAME, str(jawaban))
            print(f"  [✓] Jawaban: {jawaban}")
        else:
            print(f"  [!] Skip jawaban captcha")
        await asyncio.sleep(random.uniform(2, 3))

        # [4] Join group
        print(f"[4] Join group @{TG_GROUP}...")
        await tg_join(client, TG_GROUP, "Group")
        await asyncio.sleep(random.uniform(1, 2))

        # [5] Join channel
        print(f"[5] Join channel @{TG_CHANNEL}...")
        await tg_join(client, TG_CHANNEL, "Channel")
        await asyncio.sleep(random.uniform(1, 2))

        # [6] Follow X
        print(f"[6] Follow @{X_FOLLOW_TARGET}...")
        x_follow(auth_token, ct0, X_FOLLOW_TARGET)
        await asyncio.sleep(random.uniform(2, 3))

        # [7] Klik Done (pertama — konfirmasi join group/channel)
        print(f"[7] Klik Done (pertama)...")
        msg = await tunggu_pesan_bot(client, bot_id)
        if msg and msg.reply_markup:
            await klik_button(client, bot_id, msg.id, "done")
        await asyncio.sleep(random.uniform(2, 3))

        # [8] Klik Done (kedua)
        print(f"[8] Klik Done (kedua)...")
        msg = await tunggu_pesan_bot(client, bot_id)
        if msg and msg.reply_markup:
            await klik_button(client, bot_id, msg.id, "done")
        await asyncio.sleep(random.uniform(2, 3))

        # [9] Submit username X
        print(f"[9] Submit X username: @{x_username}...")
        await client.send_message(BOT_USERNAME, x_username)
        await asyncio.sleep(random.uniform(2, 3))

        # [10] Klik Done setelah submit usn
        print(f"[10] Klik Done setelah X username...")
        msg = await tunggu_pesan_bot(client, bot_id)
        if msg and msg.reply_markup:
            await klik_button(client, bot_id, msg.id, "done")
        await asyncio.sleep(random.uniform(2, 3))

        # [11] Submit wallet
        print(f"[11] Submit wallet: {wallet}...")
        await client.send_message(BOT_USERNAME, wallet)
        await asyncio.sleep(random.uniform(1, 2))

        msg = await tunggu_pesan_bot(client, bot_id)
        if msg and msg.text:
            print(f"  [📨] Respon akhir: {msg.text[:200]}")

    with open("shopinx_log.txt", "a") as f:
        f.write(f"{x_username}|{wallet}\n")
    print(f"  [✓] Selesai!")

# ─── MENU ──────────────────────────────────────────────────────────────────────

def menu(total):
    print("\n╔══════════════════════════════════╗")
    print("║   SHOPINX AIRDROP BOT            ║")
    print("╠══════════════════════════════════╣")
    print(f"║  Total akun: {total:<20}║")
    print("╠══════════════════════════════════╣")
    print("║  [1] 1 Akun                      ║")
    print("║  [2] Semua Akun                  ║")
    print("║  [3] Dari akun X sampai akhir    ║")
    print("╚══════════════════════════════════╝")
    pilihan = input("Pilih [1/2/3]: ").strip()

    if pilihan == "1":
        idx = int(input(f"Nomor akun (1-{total}): ").strip()) - 1
        indices = [idx]
    elif pilihan == "2":
        indices = list(range(total))
    elif pilihan == "3":
        mulai = int(input(f"Mulai dari akun ke- (1-{total}): ").strip()) - 1
        indices = list(range(mulai, total))
    else:
        print("Pilihan tidak valid.")
        sys.exit(1)

    return indices

# ─── MAIN ──────────────────────────────────────────────────────────────────────

async def main():
    if not API_ID or not API_HASH:
        print("[!] Set API_ID dan API_HASH dulu!")
        sys.exit(1)

    accounts = load_akun("akun.txt")
    sessions = load_lines("sessions.txt")
    xusns    = load_lines("usn.txt")
    wallets  = load_lines("wallet.txt")

    total = min(len(accounts), len(sessions), len(xusns))
    if total == 0:
        print("[!] Data akun kosong atau tidak lengkap")
        sys.exit(1)

    if not (len(accounts) == len(sessions) == len(xusns)):
        print(f"[!] Jumlah tidak sama — akun: {len(accounts)}, sessions: {len(sessions)}, usn: {len(xusns)}")
        print(f"    Pakai {total} akun pertama")

    indices = menu(total)
    print(f"\n[*] Menjalankan {len(indices)} akun...\n")

    for i, idx in enumerate(indices):
        wallet = wallets[idx] if idx < len(wallets) else "0x000000000000000000000000000000000000dEaD"
        await run_shopinx(
            session_string = sessions[idx],
            auth_token     = accounts[idx]["auth_token"],
            ct0            = accounts[idx]["ct0"],
            x_username     = xusns[idx],
            wallet         = wallet,
            idx            = idx,
        )

        if i < len(indices) - 1:
            delay = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
            print(f"\n[~] Cooldown {delay}s...\n")
            await asyncio.sleep(delay)

    print("\n[✓] Semua akun selesai!")
    print("[*] Log tersimpan di shopinx_log.txt")

if __name__ == "__main__":
    asyncio.run(main())
