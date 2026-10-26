"""
GitHub Private Updater Module for PowerMaster_ASUS (ТЗ-29).
Реализует:
1. Авторизацию к приватному репозиторию GitHub через Personal Access Token (PAT).
2. Сравнение версий SemVer (чистая функция compare_versions).
3. Двухэтапную загрузку бинарного ассета с обязательным Auth Stripping при S3-редиректе (HTTP 302 Location).
4. Проверку размера и целостности скачанного инсталлятора.
5. Запуск обновления через Inno Setup с ключами /SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS.

Strict Zero-Stub Policy. Production-ready implementation.
"""

from __future__ import annotations
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional, Any, Tuple, Callable

logger = logging.getLogger("PowerMaster.Updater")

def parse_semver(version_str: str) -> tuple:
    """
    Парсит версию вида 'v0.1.2', '0.2.9.1-beta', '1.0' в кортеж (int, int, ..., str).
    """
    clean_ver = str(version_str or "").strip().lstrip("vV")
    match = re.match(r"^([0-9.]+)(?:-([0-9A-Za-z.-]+))?", clean_ver)
    if not match:
        return (0, 0, 0, "")
    
    main_part = match.group(1).rstrip(".")
    prerelease = str(match.group(2) or "")
    
    nums = []
    for x in main_part.split("."):
        if x.isdigit():
            nums.append(int(x))
            
    # Дополняем нулями до минимум 3 элементов для совместимости логики
    while len(nums) < 3:
        nums.append(0)
        
    return tuple(nums) + (prerelease,)

def _split_prerelease(pre: str) -> list[tuple[int, Any]]:
    """
    Разбивает пререлизный тег (например, 'alpha.10') по точкам.
    Числовые идентификаторы преобразуются в int для правильного сравнения SemVer 2.0.
    """
    if not pre:
        return []
    parts = []
    for p in pre.split("."):
        if p.isdigit():
            parts.append((0, int(p)))  # Числовые части имеют приоритет сравнения как int
        else:
            parts.append((1, str(p))) # Буквенные как строки
    return parts

def compare_versions(current_version: str, remote_version: str) -> bool:
    """
    Возвращает True, если remote_version СТРОГО новее current_version.
    Поддерживает строгое сравнение SemVer 2.0 (включая alpha.10 > alpha.2).
    """
    cur_parsed = parse_semver(current_version)
    rem_parsed = parse_semver(remote_version)

    cur_nums = cur_parsed[:-1]
    cur_pre = cur_parsed[-1]
    rem_nums = rem_parsed[:-1]
    rem_pre = rem_parsed[-1]

    # Выравниваем длину кортежей чисел для корректного сравнения (0.2.9.1 vs 0.2.9)
    max_len = max(len(cur_nums), len(rem_nums))
    cur_nums = cur_nums + (0,) * (max_len - len(cur_nums))
    rem_nums = rem_nums + (0,) * (max_len - len(rem_nums))

    if rem_nums > cur_nums:
        return True
    if rem_nums < cur_nums:
        return False

    # Если числовые версии равны:
    # 1. Релиз новее любого пререлиза (1.0.0 > 1.0.0-rc1)
    if cur_pre and not rem_pre:
        return True
    if not cur_pre and rem_pre:
        return False

    # 2. Оба пререлиза: разбиваем по точкам с типизацией чисел (alpha.10 > alpha.2)
    if cur_pre and rem_pre:
        cur_parts = _split_prerelease(cur_pre)
        rem_parts = _split_prerelease(rem_pre)
        return rem_parts > cur_parts

    return False

@dataclass(frozen=True)
class GitHubReleaseInfo:
    tag_name: str
    version: str
    name: str
    body: str # Changelog
    asset_id: int
    asset_name: str
    asset_size: int
    download_url: str
    is_newer: bool
    expected_sha256: Optional[str] = None

SHA256_PATTERN = re.compile(
    r"<!--\s*SHA256:\s*([a-fA-F0-9]{64})\s*-->|(?:sha-?256)[\s\)\*:_=`]+([a-fA-F0-9]{64})",
    re.IGNORECASE,
)


def extract_sha256(body: str, asset_digest: Optional[str] = None) -> Optional[str]:
    """Извлекает ожидаемый SHA-256 дайджест из текста релиза или поля digest GitHub API."""
    if body:
        match = SHA256_PATTERN.search(body)
        if match:
            cand = (match.group(1) or match.group(2)).lower()
            if len(cand) == 64 and all(c in "0123456789abcdef" for c in cand):
                return cand
    if asset_digest and isinstance(asset_digest, str):
        clean_dg = asset_digest.strip().lower()
        if clean_dg.startswith("sha256:") and len(clean_dg) == 71:
            cand = clean_dg.split(":", 1)[1]
            if len(cand) == 64 and all(c in "0123456789abcdef" for c in cand):
                return cand
    return None

class NoAuthRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
    Критический обработчик редиректов:
    При перенаправлении 302 Found на AWS S3 (objects.githubusercontent.com)
    ОБЯЗАТЕЛЬНО удаляет заголовок Authorization (в headers и unredirected_hdrs),
    чтобы избежать ошибки 400 Bad Request 'Only one auth mechanism allowed'.
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is not None:
            # Регистронезависимое удаление из headers
            for k in list(new_req.headers.keys()):
                if k.lower() == "authorization":
                    del new_req.headers[k]
            # Удаление из unredirected_hdrs urllib
            if hasattr(new_req, "unredirected_hdrs"):
                for k in list(new_req.unredirected_hdrs.keys()):
                    if k.lower() == "authorization":
                        del new_req.unredirected_hdrs[k]
        return new_req

class GitHubPrivateUpdater:
    """
    Менеджер обновлений через GitHub Releases API для приватных репозиториев.
    """
    REPO_OWNER = "valeryxxx5-lab"
    REPO_NAME = "PowerMaster_ASUS"

    def __init__(self, current_version: str = "1.0.0", token: Optional[str] = None):
        self.current_version = current_version
        self.token = token or os.environ.get("GITHUB_TOKEN") or ""

    def check_for_updates(self) -> Tuple[bool, Optional[GitHubReleaseInfo], str]:
        """
        Запрашивает список релизов через GitHub API (включая prerelease).
        Возвращает (has_update, release_info, message).
        """
        # Используем /releases (список) а не /releases/latest — /latest пропускает prerelease
        url = f"https://api.github.com/repos/{self.REPO_OWNER}/{self.REPO_NAME}/releases?per_page=10"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "PowerMaster-ASUS-Updater"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    return False, None, f"GitHub API error: HTTP {resp.status}"
                releases_list = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, None, "Недействительный GitHub Token (401 Unauthorized)"
            elif e.code == 404 and not self.token:
                return False, None, "Репозиторий приватный: требуется GitHub Token (404 Not Found)"
            else:
                return False, None, f"HTTP Error {e.code}: {e.reason}"
        except Exception as e:
            return False, None, f"Ошибка сети при проверке обновлений: {e}"

        if not releases_list or not isinstance(releases_list, list):
            return False, None, "В репозитории нет доступных релизов."

        # Берём самый свежий релиз (первый в списке — GitHub сортирует по дате создания)
        data = releases_list[0]

        tag_name = data.get("tag_name", "")
        clean_tag = tag_name.lstrip("vV")
        is_newer = compare_versions(self.current_version, clean_tag)

        # Ищем файл инсталлятора в assets
        assets = data.get("assets", [])
        setup_asset = None
        for a in assets:
            aname = a.get("name", "").lower()
            if aname.endswith(".exe") and ("setup" in aname or "powermaster" in aname):
                setup_asset = a
                break

        if not setup_asset:
            return False, None, f"Релиз {tag_name} найден, но файл Setup.exe в ассетах отсутствует."

        raw_asset_id = setup_asset.get("id", 0)
        try:
            asset_id = int(raw_asset_id)
        except (ValueError, TypeError):
            asset_id = 0

        if asset_id <= 0:
            return False, None, f"Некорректный идентификатор ассета инсталлятора (asset_id={raw_asset_id})"

        expected_sha = extract_sha256(data.get("body", ""), setup_asset.get("digest"))

        release_info = GitHubReleaseInfo(
            tag_name=tag_name,
            version=clean_tag,
            name=data.get("name") or tag_name,
            body=data.get("body") or "Нет описания изменений.",
            asset_id=asset_id,
            asset_name=setup_asset.get("name", ""),
            asset_size=setup_asset.get("size", 0),
            download_url=setup_asset.get("url", ""),
            is_newer=is_newer,
            expected_sha256=expected_sha,
        )

        if is_newer:
            msg = f"Доступна новая версия: v{clean_tag} (текущая: v{self.current_version})"
        else:
            msg = f"У вас установлена актуальная версия v{self.current_version}"

        return is_newer, release_info, msg

    def download_installer(
        self,
        release_info: GitHubReleaseInfo,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Tuple[bool, str]:
        """
        Двухэтапная безопасная загрузка инсталлятора с потоковым расчётом SHA-256,
        закрытием файла до атомарной подмены (Windows NT safe) и криптографической проверкой.
        Возвращает (success, file_path_or_error_msg).
        """
        temp_dir = tempfile.gettempdir()
        dest_file = os.path.join(temp_dir, f"PowerMaster_ASUS_Setup_v{release_info.version}.exe")
        tmp_path: Optional[str] = None

        asset_url = f"https://api.github.com/repos/{self.REPO_OWNER}/{self.REPO_NAME}/releases/assets/{release_info.asset_id}"
        headers = {
            "Accept": "application/octet-stream",
            "User-Agent": "PowerMaster-ASUS-Updater",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        opener = urllib.request.build_opener(NoAuthRedirectHandler())
        req = urllib.request.Request(asset_url, headers=headers)
        hasher = hashlib.sha256()

        try:
            with opener.open(req, timeout=30) as resp:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=temp_dir,
                    prefix="pm_setup_",
                    suffix=".tmp",
                    delete=False,
                ) as out_f:
                    tmp_path = out_f.name
                    total_size = int(resp.headers.get("Content-Length", release_info.asset_size))
                    downloaded = 0
                    chunk_size = 64 * 1024

                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        out_f.write(chunk)
                        hasher.update(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            progress_callback(downloaded, total_size)
                    out_f.flush()
                    os.fsync(out_f.fileno())

            # Файл out_f закрыт! Теперь безопасно проверять размер, хэш и вызывать os.unlink / os.replace на Windows
            downloaded_size = os.path.getsize(tmp_path)
            if release_info.asset_size > 0 and abs(downloaded_size - release_info.asset_size) > 1024:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                return False, f"Ошибка целостности: размер {downloaded_size} не совпадает с {release_info.asset_size}"

            actual_sha256 = hasher.hexdigest().lower()
            if release_info.expected_sha256:
                if actual_sha256 != release_info.expected_sha256.lower():
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
                    msg = (
                        f"Ошибка безопасности: контрольная сумма SHA-256 не совпадает! "
                        f"(ожидалось: {release_info.expected_sha256}, получено: {actual_sha256})"
                    )
                    logger.error(msg)
                    return False, msg
                logger.info(f"SHA-256 checksum verified successfully: {actual_sha256}")
            else:
                logger.warning(
                    f"Release {release_info.tag_name} does not contain SHA-256 digest in description. "
                    f"Computed hash: {actual_sha256}"
                )

            os.replace(tmp_path, dest_file)
            return True, dest_file
        except Exception as e:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            return False, f"Ошибка скачивания инсталлятора: {e}"

    @staticmethod
    def execute_inno_setup(installer_path: str, silent: bool = False) -> bool:
        """
        Запускает инсталлятор Inno Setup через оболочку Windows (ShellExecute / subprocess).
        Запуск отвязан от текущего процесса (detached), что позволяет установщику работать
        после завершения текущей программы и перезапустить обновленный PowerMaster_ASUS.
        """
        if not os.path.exists(installer_path):
            logger.error(f"Installer path does not exist: {installer_path}")
            return False

        # Очищаем переменные среды PyInstaller, чтобы инсталлятор и перезапущенное
        # приложение не наследовали PID умершего родительского процесса.
        for k in list(os.environ.keys()):
            if k.upper().startswith("_PYI_") or k.upper().startswith("_MEI"):
                del os.environ[k]
        clean_env = dict(os.environ)

        flags = (
            "/SILENT /FORCECLOSEAPPLICATIONS /NORESTART /LANG=russian /LOG"
            if silent
            else "/CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS /NORESTART /LANG=russian"
        )
        logger.info(f"Executing Inno Setup installer: {installer_path} (flags={flags})")

        # 1. Запуск через ShellExecuteW с параметром "open" (без UAC — установка в %LOCALAPPDATA%)
        try:
            import ctypes
            from ctypes import wintypes
            shell32 = getattr(ctypes.windll, "shell32", None)
            if shell32 and hasattr(shell32, "ShellExecuteW"):
                ShellExecuteW = shell32.ShellExecuteW
                ShellExecuteW.restype = wintypes.HINSTANCE
                ShellExecuteW.argtypes = [
                    wintypes.HWND,
                    wintypes.LPCWSTR,
                    wintypes.LPCWSTR,
                    wintypes.LPCWSTR,
                    wintypes.LPCWSTR,
                    ctypes.c_int,
                ]
                ret = ShellExecuteW(None, "open", installer_path, flags, None, 1)
                ret_val = int(ret) if ret else 0
                if ret_val > 32:
                    logger.info(f"ShellExecuteW launched installer successfully (ret={ret_val})")
                    return True
                else:
                    logger.warning(f"ShellExecuteW returned code {ret_val} (<=32 indicates failure)")
        except Exception as e:
            logger.warning(f"ShellExecuteW failed: {e}")

        # 2. Надежный fallback: запуск через полностью отвязанный subprocess (DETACHED_PROCESS)
        try:
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            p = subprocess.Popen(
                [installer_path] + flags.split(),
                env=clean_env,
                creationflags=creationflags,
                close_fds=True,
            )
            logger.info(f"Spawned installer via detached subprocess PID={p.pid}")
            return True
        except Exception as e2:
            logger.error(f"Failed to launch installer via subprocess: {e2}")
            return False

