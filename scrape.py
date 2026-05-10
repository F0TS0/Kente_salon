#!/usr/bin/env python3
"""Decrypt Chrome's Instagram cookies and download kentesalon posts via instaloader."""
import hashlib
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import instaloader
from Crypto.Cipher import AES

CHROME_DEFAULT = Path.home() / "Library/Application Support/Google/Chrome/Default"
TARGET_PROFILE = "jaythabarber7"


def get_chrome_password() -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-w", "-a", "Chrome", "-s", "Chrome Safe Storage"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def derive_key(password: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha1", password.encode(), b"saltysalt", 1003, 16)


def decrypt_cookie(encrypted: bytes, key: bytes) -> str:
    if not encrypted.startswith(b"v10"):
        return encrypted.decode("utf-8", errors="replace")
    cipher = AES.new(key, AES.MODE_CBC, b" " * 16)
    decrypted = cipher.decrypt(encrypted[3:])
    pad = decrypted[-1]
    decrypted = decrypted[:-pad]
    # Modern Chrome (M130+ on macOS) prepends a 32-byte SHA-256 of the host_key
    # to the plaintext. Try stripping it; if the result isn't sensible text,
    # fall back to the raw plaintext (older Chrome format).
    for candidate in (decrypted[32:], decrypted):
        try:
            text = candidate.decode("utf-8")
            if all(c.isprintable() or c == " " for c in text):
                return text
        except UnicodeDecodeError:
            continue
    return decrypted.decode("utf-8", errors="replace")


def load_instagram_cookies() -> dict[str, str]:
    src = CHROME_DEFAULT / "Cookies"
    tmp = Path("/tmp/_chrome_cookies_copy.db")
    shutil.copy(src, tmp)

    key = derive_key(get_chrome_password())

    conn = sqlite3.connect(str(tmp))
    cur = conn.execute(
        "SELECT name, value, encrypted_value FROM cookies "
        "WHERE host_key LIKE '%instagram.com'"
    )
    cookies: dict[str, str] = {}
    for name, value, enc in cur.fetchall():
        if value:
            cookies[name] = value
        else:
            try:
                cookies[name] = decrypt_cookie(enc, key)
            except Exception as e:
                print(f"  ! decrypt failed for {name}: {e}", file=sys.stderr)
    conn.close()
    tmp.unlink()
    return cookies


def main() -> None:
    print("Reading Instagram cookies from Chrome (Default profile)...")
    print("(macOS may show a Keychain prompt — click Always Allow.)")
    cookies = load_instagram_cookies()
    print(f"  loaded {len(cookies)} cookies: {sorted(cookies.keys())}")
    for name, value in sorted(cookies.items()):
        preview = value if len(value) <= 24 else value[:24] + "..."
        # Safe ASCII preview so a corrupted value doesn't blow up the print
        safe = preview.encode("ascii", errors="backslashreplace").decode("ascii")
        print(f"    {name} = {safe}  (len={len(value)})")

    if "sessionid" not in cookies:
        sys.exit("ERROR: no sessionid cookie — log into Instagram in Chrome first.")

    L = instaloader.Instaloader(
        download_videos=False,
        download_video_thumbnails=False,
        dirname_pattern="downloads/{profile}",
        save_metadata=False,
    )
    for name, value in cookies.items():
        L.context._session.cookies.set(name, value, domain=".instagram.com")

    username = L.test_login()
    if not username:
        sys.exit("ERROR: cookies did not authenticate. Re-login in Chrome and retry.")
    print(f"Authenticated as: {username}")
    L.context.username = username

    print(f"Downloading photos from @{TARGET_PROFILE}...")
    L.download_profile(TARGET_PROFILE, profile_pic_only=False)
    print("Done.")


if __name__ == "__main__":
    main()
