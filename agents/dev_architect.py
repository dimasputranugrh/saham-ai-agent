import json
import os
import py_compile
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional
import requests
from google import genai
from google.genai import types

import config

PROJECT_ROOT = config.BASE_DIR

CORE_PROJECT_FILES = [
    "config.py",
    "main.py",
    "cloud_runner.py",
    "agents/team.py",
    "agents/ai_panel.py",
    "bot/telegram_bot.py",
    "analyzer/technical.py",
    "analyzer/news.py",
    "memory/database.py",
    "memory/evaluator.py",
    "memory/learning_loop.py",
    "memory/performance.py",
    "memory/retrieval.py",
    ".github/workflows/jadwal_saham_otomatis.yml",
]

FORBIDDEN_PATHS = {".env", ".git"}


def is_authorized_owner(chat_id: int | str | None) -> bool:
    """Memastikan hanya pemilik resmi (TELEGRAM_CHAT_ID Bos) yang boleh memakai /agy dan /upgrade."""
    if chat_id is None:
        return True
    owner_id = str(config.TELEGRAM_CHAT_ID or "").strip()
    if not owner_id or owner_id.startswith("masukkan_"):
        return True
    return str(chat_id).strip() == owner_id


def _find_agy_binary() -> Optional[str]:
    """Mencari lokasi binary Antigravity CLI (agy) di WSL lokal."""
    candidates = [
        "/home/dimas/.local/bin/agy",
        "/home/dimas/.gemini/antigravity-cli/bin/agy",
        shutil.which("agy") or "",
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def _call_local_agy_argon(prompt: str, allow_edits: bool = False, timeout_sec: int = 90) -> Optional[str]:
    """
    Memanggil Antigravity CLI (`agy`) asli dengan model `gemini-4-argon` saat berjalan di WSL lokal!
    """
    if os.getenv("GITHUB_ACTIONS") == "true":
        return None
    agy_bin = _find_agy_binary()
    if not agy_bin:
        return None
    cmd = [agy_bin, "--model", "gemini-4-argon"]
    if allow_edits:
        cmd.extend(["--mode", "accept-edits", "--dangerously-skip-permissions"])
    cmd.extend(["-p", prompt])
    try:
        res = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        if res.returncode == 0 and res.stdout and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return None


def _call_architect_llm(system_prompt: str, user_prompt: str, temperature: float = 0.15) -> tuple[Optional[str], str]:
    """
    Memanggil otak AI Architect:
    - Prioritas 0 (Saat di WSL Lokal): Antigravity CLI `gemini-4-argon`
    - Prioritas 1 (Cloud / Fallback): Google `gemini-3.6-flash`
    - Prioritas 2 (Cloud / Fallback): OpenAI `openai/gpt-oss-120b` (via Groq)
    """
    # 0. Jika di WSL Lokal dan binary `agy` tersedia, gunakan langsung `gemini-4-argon`!
    agy_out = _call_local_agy_argon(f"{system_prompt}\n\n{user_prompt}", allow_edits=False, timeout_sec=60)
    if agy_out:
        return agy_out, "gemini-4-argon (via Antigravity CLI)"

    # 1. Coba Gemini 3.6 Flash / 3 Flash Preview
    gem_key = config.GEMINI_API_KEY
    if gem_key and not gem_key.startswith("masukkan_"):
        try:
            client = genai.Client(
                api_key=gem_key,
                http_options=types.HttpOptions(
                    timeout=20000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            for mod in ["gemini-3.6-flash", "gemini-3-flash-preview", "gemini-3.5-flash-lite"]:
                try:
                    resp = client.models.generate_content(
                        model=mod,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=temperature,
                        ),
                    )
                    if resp and resp.text:
                        return resp.text.strip(), mod
                except Exception:
                    continue
        except Exception:
            pass

    # 2. Fallback ke Groq (OpenAI 120B / Alibaba Qwen 3.8)
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        for mod in ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]:
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={
                        "model": mod,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                    },
                    timeout=20,
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip(), f"groq:{mod}"
            except Exception:
                continue
    return None, "unavailable"


def _select_relevant_files(query: str, max_files: int = 5) -> dict[str, str]:
    """Memilih file project yang paling relevan dengan pertanyaan/instruksi upgrade dari Bos."""
    q_lower = query.lower()
    scored: list[tuple[int, str]] = []
    for rel_path in CORE_PROJECT_FILES:
        full_p = PROJECT_ROOT / rel_path
        if not full_p.exists():
            continue
        score = 1
        base = Path(rel_path).name.lower()
        if base in q_lower or rel_path.lower() in q_lower:
            score += 10
        if any(k in q_lower for k in ["ai", "panel", "voting", "rapor", "ganti"]) and "ai_panel" in rel_path:
            score += 6
        if any(k in q_lower for k in ["telegram", "command", "perintah", "jadwal", "jam", "bot"]) and (
            "telegram_bot" in rel_path or "cloud_runner" in rel_path
        ):
            score += 6
        if any(k in q_lower for k in ["watchlist", "sektor", "fee", "biaya", "config", "setting"]) and "config" in rel_path:
            score += 6
        if any(k in q_lower for k in ["rumus", "vwap", "rsi", "macd", "indikator", "teknikal"]) and "technical" in rel_path:
            score += 6
        if any(k in q_lower for k in ["database", "db", "memori", "sqlite", "tabel"]) and "memory/" in rel_path:
            score += 5
        if any(k in q_lower for k in ["dsu", "budi", "sari", "hendra", "arif", "laporan"]) and "team.py" in rel_path:
            score += 5
        scored.append((score, rel_path))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected: dict[str, str] = {}
    for _, rel_path in scored[:max_files]:
        try:
            text = (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")
            # Batasi ukuran per file agar konteks efisien
            selected[rel_path] = text[:14000]
        except Exception:
            pass
    return selected


def ask_project_architect(question: str, chat_id: int | str | None = None) -> str:
    """
    Menjawab pertanyaan teknis/arsitektur tentang project saham-ai-agent dari Telegram (/agy).
    Bisa berjalan di WSL (via Antigravity CLI atau LLM Architect) maupun di GitHub Actions Cloud!
    """
    if not is_authorized_owner(chat_id):
        return "⛔ Akses ditolak. Perintah `/agy` hanya bisa dijalankan oleh pemilik project."

    if not question.strip():
        return (
            "🤖 *Jembatan Telegram ↔ Antigravity Architect Aktif!*\n\n"
            "Bos bisa bertanya apa saja tentang isi project ini atau meminta upgrade fitur langsung dari Telegram:\n"
            "• *Tanya Project:* `/agy jelaskan cara kerja 5 AI dan database memori di project ini`\n"
            "• *Upgrade Kode Otomatis:* `/upgrade tambahkan saham BRIS.JK ke daftar SECTOR_MAP di config.py`\n\n"
            "_Berfungsi penuh baik saat Laptop Nyala (WSL) maupun saat Laptop Mati (GitHub Cloud)!_"
        )

    mode_env = "☁️ GitHub Cloud" if os.getenv("GITHUB_ACTIONS") == "true" else "💻 WSL Lokal"
    files_ctx = _select_relevant_files(question, max_files=5)

    sys_prompt = (
        "Anda adalah Antigravity AI Architect yang menjaga project `saham-ai-agent` milik Bos Dimas.\n"
        "Jawab pertanyaan Bos tentang project ini dengan bahasa Indonesia yang ramah, jelas, dan mudah dipahami ('Bahasa Bayi' bila menyangkut istilah rumit), "
        "namun tetap menyebutkan nama file dan fungsi yang relevan secara akurat.\n"
        f"Saat ini Anda menjawab dari lingkungan: {mode_env}."
    )
    user_prompt = (
        f"Pertanyaan Bos: {question}\n\n"
        f"Daftar seluruh file utama di project:\n{json.dumps(CORE_PROJECT_FILES, indent=2)}\n\n"
        f"Isi file kode yang relevan:\n{json.dumps(files_ctx, ensure_ascii=False)}"
    )

    ans, used_model = _call_architect_llm(sys_prompt, user_prompt, temperature=0.2)
    if ans:
        return (
            f"🤖 *Antigravity Architect ({mode_env})*\n"
            f"🧠 _Model: `{used_model}`_\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{ans}"
        )
    return "⚠️ Maaf Bos, koneksi ke server AI Architect sedang sibuk. Silakan coba beberapa saat lagi."


def _parse_json_object(raw: str) -> Optional[dict[str, Any]]:
    if not raw:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except Exception:
            pass
    return None


def upgrade_project_code(instruction: str, chat_id: int | str | None = None) -> str:
    """
    Menerima instruksi `/upgrade <perintah>` dari Telegram, mengedit kode project secara aman,
    menjalankan tes kompilasi Python (`py_compile`), melakukan auto-rollback jika ada error,
    dan otomatis commit + push ke GitHub jika 100% sukses!
    """
    if not is_authorized_owner(chat_id):
        return "⛔ Akses ditolak. Hanya pemilik project yang boleh menjalankan `/upgrade`."

    if not instruction.strip():
        return (
            "🛠️ *Fitur Auto-Upgrade Project dari Telegram (`/upgrade`)*\n\n"
            "Ketik perubahan atau fitur yang Bos inginkan, contoh:\n"
            "• `/upgrade tambahkan saham BRIS.JK dan TPIA.JK ke SECTOR_MAP di config.py`\n"
            "• `/upgrade ubah MIN_INTRADAY_ALERT_SCORE default di config.py menjadi 70`\n"
            "• `/upgrade tambahkan sapaan semangat pagi di awal laporan DSU`\n\n"
            "🛡️ *Keamanan:* Setiap perubahan akan diuji otomatis (`Syntax & Compile Check`). "
            "Jika lolos tes, otomatis di-*commit & push* ke GitHub. Jika ada error, otomatis dibatalkan (*Rollback*)."
        )

    mode_env = "☁️ GitHub Cloud" if os.getenv("GITHUB_ACTIONS") == "true" else "💻 WSL Lokal"
    files_ctx = _select_relevant_files(instruction, max_files=4)

    sys_prompt = (
        "Anda adalah Senior Python Architect yang melakukan upgrade kode otomatis pada project `saham-ai-agent`.\n"
        "ATURAN KESELAMATAN KERAS:\n"
        "1. DILARANG mengubah atau membaca file `.env` atau membocorkan API key.\n"
        "2. DILARANG mengaktifkan live broker trading tanpa izin.\n"
        "3. Buat perubahan yang bersih, minimal, dan 100% valid secara sintaks Python.\n"
        "4. Balas HANYA dalam format JSON valid dengan struktur persis berikut:\n"
        "{\n"
        '  "summary": "Penjelasan singkat apa yang di-upgrade untuk Bos",\n'
        '  "edits": [\n'
        "    {\n"
        '      "file": "path/relatif/file.py",\n'
        '      "target": "potongan kode lama yang persis ingin diganti",\n'
        '      "replacement": "potongan kode baru penggantinya"\n'
        "    }\n"
        "  ]\n"
        "}"
    )
    user_prompt = (
        f"Instruksi Upgrade dari Bos:\n{instruction}\n\n"
        f"Isi file-file project saat ini:\n{json.dumps(files_ctx, ensure_ascii=False)}"
    )

    raw_resp, used_model = _call_architect_llm(sys_prompt, user_prompt, temperature=0.1)
    plan = _parse_json_object(raw_resp or "")
    if not plan or not isinstance(plan.get("edits"), list) or not plan["edits"]:
        return (
            f"⚠️ *Upgrade Dibatalkan dengan Aman ({mode_env}):*\n"
            "AI Architect belum menemukan bagian kode yang pas untuk diubah dari instruksi tersebut. "
            "Coba sebutkan lebih spesifik (misal nama file atau fitur yang ingin diubah)."
        )

    edits = plan["edits"]
    summary = str(plan.get("summary", "Pembaruan kode selesai."))
    backups: dict[Path, str] = {}
    modified_files: list[str] = []

    try:
        for edit in edits:
            rel_file = str(edit.get("file", "")).strip().lstrip("/")
            target = str(edit.get("target", ""))
            replacement = str(edit.get("replacement", ""))
            if not rel_file or any(bad in rel_file for bad in FORBIDDEN_PATHS) or ".." in rel_file:
                raise ValueError(f"File `{rel_file}` dilindungi dan tidak boleh diubah.")

            full_path = (PROJECT_ROOT / rel_file).resolve()
            if not str(full_path).startswith(str(PROJECT_ROOT.resolve())):
                raise ValueError("Path file di luar direktori project.")
            if not full_path.exists():
                raise ValueError(f"File `{rel_file}` tidak ditemukan.")

            original_content = full_path.read_text(encoding="utf-8")
            if not target or target not in original_content:
                raise ValueError(f"Target kode pada `{rel_file}` tidak cocok persis dengan isi file saat ini.")

            if full_path not in backups:
                backups[full_path] = original_content

            new_content = original_content.replace(target, replacement, 1)
            full_path.write_text(new_content, encoding="utf-8")
            if rel_file not in modified_files:
                modified_files.append(rel_file)

        # Uji kompilasi sintaks Python untuk semua file .py yang disentuh
        for rel_file in modified_files:
            if rel_file.endswith(".py"):
                py_compile.compile(str(PROJECT_ROOT / rel_file), doraise=True)

    except Exception as e:
        # AUTO-ROLLBACK: Kembalikan semua file ke kondisi semula!
        for fpath, old_txt in backups.items():
            fpath.write_text(old_txt, encoding="utf-8")
        return (
            f"🛡️ *Auto-Rollback Aktif ({mode_env}):*\n"
            f"Perubahan dibatalkan otomatis agar bot tidak rusak karena gagal validasi: `{e}`"
        )

    # Commit & Push otomatis ke GitHub agar Laptop & Cloud tetap sinkron
    push_status = "Tersimpan di lokal"
    try:
        subprocess.run(["git", "add"] + modified_files, cwd=str(PROJECT_ROOT), check=False, timeout=10)
        commit_msg = f"feat(telegram-upgrade): {instruction[:60]}"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(PROJECT_ROOT), check=False, timeout=10)
        res = subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=20)
        if res.returncode == 0:
            push_status = "✅ Otomatis di-commit & di-push ke GitHub (`origin/main`)!"
        else:
            push_status = "⚠️ Berhasil di-commit lokal (menunggu sinkronisasi GitHub)."
    except Exception:
        pass

    files_str = ", ".join([f"`{f}`" for f in modified_files])
    return (
        f"🚀 *UPGRADE PROJECT BERHASIL ({mode_env})!*\n"
        f"🧠 _Model: `{used_model}`_\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Ringkasan Upgrade:* {summary}\n"
        f"• *File yang Diperbarui:* {files_str}\n"
        f"• *Uji Sintaks Python:* ✅ Lolos 100% Tanpa Error\n"
        f"• *Status GitHub:* {push_status}"
    )
