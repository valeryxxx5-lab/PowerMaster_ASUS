import unittest
import sys
import os
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from updater import compare_versions, parse_semver, GitHubPrivateUpdater, NoAuthRedirectHandler
from icon_generator import IconSpeedMetaphorGenerator

class TestUpdaterAndIconsTZ29(unittest.TestCase):

    def test_1_semver_parsing_and_comparison(self):
        """
        Тест 1 (Релизная логика): Сравнение версий по стандарту SemVer 2.0.
        """
        self.assertEqual(parse_semver("v1.0.0"), (1, 0, 0, ""))
        self.assertEqual(parse_semver("0.2.1-beta"), (0, 2, 1, "beta"))
        
        # 0.2.0 новее 0.1.1
        self.assertTrue(compare_versions("0.1.1", "0.2.0"))
        # 1.0.0 новее 0.9.9
        self.assertTrue(compare_versions("0.9.9", "1.0.0"))
        # Версии равны
        self.assertFalse(compare_versions("1.0.0", "1.0.0"))
        # Старая версия не новее текущей
        self.assertFalse(compare_versions("1.1.0", "1.0.9"))
        # Релиз новее пререлиза
        self.assertTrue(compare_versions("1.0.0-rc1", "1.0.0"))
        # Замечание Jules-1: alpha.10 СТРОГО новее alpha.2 по SemVer 2.0
        self.assertTrue(compare_versions("1.0.0-alpha.2", "1.0.0-alpha.10"))
        self.assertFalse(compare_versions("1.0.0-alpha.10", "1.0.0-alpha.2"))

    def test_2_no_auth_redirect_handler_strips_authorization_header(self):
        """
        Тест 2 (Безопасность S3): Проверка удаления заголовка Authorization при 302 Found.
        Предотвращает фатальную ошибку AWS S3: 400 Bad Request 'Only one auth mechanism allowed'.
        """
        import urllib.request
        handler = NoAuthRedirectHandler()
        
        # Создаем исходный запрос с Bearer токеном
        req = urllib.request.Request(
            "https://api.github.com/repos/valeryxxx5-lab/PowerMaster_ASUS/releases/assets/12345",
            headers={"Authorization": "Bearer test_secret_pat_token", "Accept": "application/octet-stream"}
        )
        self.assertIn("Authorization", req.headers)

        # Симулируем обработку редиректа на AWS S3
        redirected_req = handler.redirect_request(
            req=req,
            fp=None,
            code=302,
            msg="Found",
            headers={},
            newurl="https://objects.githubusercontent.com/github-production-release-asset-2e65be/installer.exe"
        )
        
        # Заголовок Authorization ОБЯЗАН быть удален из перенаправленного запроса!
        self.assertNotIn("Authorization", redirected_req.headers)
        self.assertNotIn("authorization", redirected_req.headers)

    def test_3_rocket_icon_generation_64x64(self):
        """
        Тест 3 (Внешний вид): Генерация иконки Ракеты (High Performance).
        Проверка размера 64x64, режима RGBA и непрозрачности.
        """
        img_ac = IconSpeedMetaphorGenerator.draw_rocket_icon(is_ac=True, has_update=True)
        self.assertIsInstance(img_ac, Image.Image)
        self.assertEqual(img_ac.size, (64, 64))
        self.assertEqual(img_ac.mode, "RGBA")

        img_batt = IconSpeedMetaphorGenerator.draw_rocket_icon(is_ac=False, has_update=False)
        self.assertEqual(img_batt.size, (64, 64))

    def test_4_car_icon_generation_64x64(self):
        """
        Тест 4 (Внешний вид): Генерация иконки Автомобиля (Balanced).
        """
        img = IconSpeedMetaphorGenerator.draw_car_icon(is_ac=True, has_update=False)
        self.assertEqual(img.size, (64, 64))
        self.assertEqual(img.mode, "RGBA")

    def test_5_bicycle_icon_generation_64x64(self):
        """
        Тест 5 (Внешний вид): Генерация иконки Велосипеда (Power Saver).
        """
        img = IconSpeedMetaphorGenerator.draw_bicycle_icon(is_ac=False, has_update=True)
        self.assertEqual(img.size, (64, 64))
        self.assertEqual(img.mode, "RGBA")

    def test_6_icon_factory_router(self):
        """
        Тест 6: Фабричный метод генерации иконки под имя плана.
        """
        i_rocket = IconSpeedMetaphorGenerator.generate_icon("High Performance", is_ac=True)
        i_car = IconSpeedMetaphorGenerator.generate_icon("Balanced", is_ac=True)
        i_bike = IconSpeedMetaphorGenerator.generate_icon("Power Saver", is_ac=False)
        
        self.assertEqual(i_rocket.size, (64, 64))
        self.assertEqual(i_car.size, (64, 64))
        self.assertEqual(i_bike.size, (64, 64))

    def test_7_inno_setup_command_generation(self):
        """
        Тест 7: Проверка генерации ключей запуска Inno Setup.
        """
        from unittest.mock import patch
        setup_exe = "C:\\Temp\\PowerMaster_Setup.exe"

        # Test silent mode fallback to subprocess
        with patch('updater.subprocess.Popen') as mock_popen, \
             patch('updater.os.path.exists', return_value=True):
            # Also mock ctypes to trigger the fallback
            with patch.dict('sys.modules', {'ctypes': None}):
                GitHubPrivateUpdater.execute_inno_setup(setup_exe, silent=True)
                mock_popen.assert_called_once()
                args = mock_popen.call_args[0][0]
                self.assertEqual(args[0], setup_exe)
                self.assertIn("/SILENT", args)
                self.assertIn("/FORCECLOSEAPPLICATIONS", args)
                self.assertIn("/NORESTART", args)

        # Test non-silent mode
        with patch('updater.subprocess.Popen') as mock_popen, \
             patch('updater.os.path.exists', return_value=True):
            with patch.dict('sys.modules', {'ctypes': None}):
                GitHubPrivateUpdater.execute_inno_setup(setup_exe, silent=False)
                mock_popen.assert_called_once()
                args = mock_popen.call_args[0][0]
                self.assertEqual(args[0], setup_exe)
                self.assertIn("/CLOSEAPPLICATIONS", args)
                self.assertIn("/FORCECLOSEAPPLICATIONS", args)
                self.assertIn("/NORESTART", args)

    def test_8_tile_icon_generation_and_coverage(self):
        """
        Тест 8 (Огромная плитка): Проверка генерации плиточных иконок 64x64 и заполнения >85% площади.
        """
        for plan, is_ac, has_upd in [
            ("High Performance", True, False),
            ("07fa2daf-30e4-41ad-8daf-5bf18a330c48", False, True),
            ("Balanced", True, True),
            ("Power Saver", False, False),
            ("d6c42cfd-bf64-4edf-85e4-9b82cd8789d8", True, False),
        ]:
            img = IconSpeedMetaphorGenerator.draw_tile_icon(plan, is_ac=is_ac, has_update=has_upd)
            self.assertEqual(img.size, (64, 64))
            self.assertEqual(img.mode, "RGBA")
            # Подсчет непрозрачных пикселей (должно быть >= 85% площади 64x64)
            non_trans = sum(1 for p in img.getdata() if p[3] > 0)
            coverage = non_trans / (64 * 64)
            self.assertGreater(coverage, 0.85, f"Tile icon for {plan} must fill at least 85% of area, got {coverage*100:.1f}%")

    def test_9_update_dialog_dark_theme_and_formatting(self):
        """
        Тест 9: Проверка темной темы, форматирования changelog и отсутствия белых полей в UpdateDialog.
        """
        from unittest.mock import MagicMock, patch
        from update_dialog import UpdateDialog, DIALOG_SCALES
        from updater import GitHubReleaseInfo

        mock_updater = MagicMock()
        mock_updater.current_version = "0.2.14-beta"

        rel_info = GitHubReleaseInfo(
            tag_name="v0.2.15-beta",
            version="0.2.15-beta",
            name="v0.2.15-beta",
            body="## What's Changed\n- 🚀 **Performance:** Fast boot\n- 🎨 **Theme:** Deep dark",
            asset_id=12345,
            asset_name="PowerMaster_ASUS_Setup_v0.2.15-beta.exe",
            asset_size=22000000,
            download_url="https://example.com/asset.exe",
            is_newer=True
        )

        with patch('tkinter.Tk') as mock_tk_cls, \
             patch('tkinter.Toplevel') as mock_top_cls, \
             patch('tkinter.DoubleVar') as mock_dvar, \
             patch('tkinter.Text') as mock_txt_cls, \
             patch('tkinter.ttk.Style') as mock_style_cls, \
             patch('update_dialog.config') as mock_cfg:

            mock_root = MagicMock()
            mock_root.winfo_screenwidth.return_value = 1920
            mock_root.winfo_screenheight.return_value = 1080
            mock_tk_cls.return_value = mock_root
            mock_top_cls.return_value = mock_root
            mock_txt = MagicMock()
            mock_txt_cls.return_value = mock_txt

            mock_cfg.ui_theme = "oled_contrast"
            mock_cfg.ui_scale = 1.0

            dlg = UpdateDialog(mock_updater, rel_info)

            # Проверка соответствия темной темы OLED
            self.assertEqual(dlg.theme["bg_main"], "#000000")
            self.assertEqual(dlg.theme["bg_card_inner"], "#161616")
            self.assertEqual(dlg.theme["fg_main"], "#ffffff")

            # Проверка масштабов геометрии
            self.assertEqual(dlg.scale_data["win_w"], 540)
            self.assertEqual(dlg.scale_data["win_h"], 450)

            # Проверка параметров создания Text виджета под темную тему (не белый #F5F6FA!)
            mock_txt_cls.assert_called_once()
            kw = mock_txt_cls.call_args[1]
            self.assertEqual(kw["bg"], "#161616")
            self.assertEqual(kw["fg"], "#ffffff")

            # Проверка форматирования текста (h1, bullet, bold)
            mock_txt.tag_configure.assert_any_call("h1", font=("Segoe UI", 11, "bold"), foreground="#00ffff", spacing3=4)
            mock_txt.tag_configure.assert_any_call("bullet", font=("Segoe UI", 9, "bold"), foreground="#00ffff")

            dlg._on_close()

    def test_10_extract_sha256_patterns(self):
        from updater import extract_sha256
        sample_hash = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
        
        # 1. HTML comment format
        b1 = f"Some text\n<!-- SHA256: {sample_hash} -->\n"
        self.assertEqual(extract_sha256(b1), sample_hash)

        # 2. Markdown bold list format with backticks
        b2 = f"- **PowerMaster_ASUS_Setup.exe (SHA-256)**: `{sample_hash}`"
        self.assertEqual(extract_sha256(b2), sample_hash)

        # 3. Simple header format
        b3 = f"SHA256: {sample_hash}"
        self.assertEqual(extract_sha256(b3), sample_hash)

        # 4. GitHub API asset digest
        digest = f"sha256:{sample_hash}"
        self.assertEqual(extract_sha256("", digest), sample_hash)

        # 5. Invalid / missing cases
        self.assertIsNone(extract_sha256("No hash in body here"))
        self.assertIsNone(extract_sha256("", "md5:1234"))
        self.assertIsNone(extract_sha256("", None))

    def test_11_check_for_updates_invalid_asset_id(self):
        from updater import GitHubPrivateUpdater
        from unittest.mock import patch, MagicMock
        import json

        updater = GitHubPrivateUpdater(current_version="0.2.0")

        # Mock response with negative asset id
        mock_releases = [{
            "tag_name": "v0.3.0",
            "assets": [{"name": "PowerMaster_ASUS_Setup.exe", "id": -5, "size": 1000}]
        }]

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_releases).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            has_update, rel_info, msg = updater.check_for_updates()
            self.assertFalse(has_update)
            self.assertIsNone(rel_info)
            self.assertIn("Некорректный идентификатор ассета", msg)

    def test_12_download_installer_sha256_verification_and_mismatch(self):
        from updater import GitHubPrivateUpdater, GitHubReleaseInfo
        from unittest.mock import patch, MagicMock
        import hashlib
        import os

        updater = GitHubPrivateUpdater(current_version="0.2.0")
        sample_payload = b"Fake installer binary content for testing SHA256"
        valid_sha = hashlib.sha256(sample_payload).hexdigest()
        invalid_sha = "0000000000000000000000000000000000000000000000000000000000000000"

        # Case 1: Mismatch triggers error and securely unlinks file
        info_mismatch = GitHubReleaseInfo(
            tag_name="v0.3.0",
            version="0.3.0",
            name="Release 0.3.0",
            body="test",
            asset_id=123,
            asset_name="PowerMaster_ASUS_Setup.exe",
            asset_size=len(sample_payload),
            download_url="http://mock",
            is_newer=True,
            expected_sha256=invalid_sha
        )

        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Length": str(len(sample_payload))}
        mock_resp.read.side_effect = [sample_payload, b""]
        mock_resp.__enter__.return_value = mock_resp

        mock_opener = MagicMock()
        mock_opener.open.return_value.__enter__.return_value = mock_resp

        with patch("urllib.request.build_opener", return_value=mock_opener):
            ok, err = updater.download_installer(info_mismatch)
            self.assertFalse(ok)
            self.assertIn("контрольная сумма SHA-256 не совпадает", err)

        # Case 2: Matching hash succeeds
        info_match = GitHubReleaseInfo(
            tag_name="v0.3.0",
            version="0.3.0",
            name="Release 0.3.0",
            body="test",
            asset_id=123,
            asset_name="PowerMaster_ASUS_Setup.exe",
            asset_size=len(sample_payload),
            download_url="http://mock",
            is_newer=True,
            expected_sha256=valid_sha
        )

        mock_resp2 = MagicMock()
        mock_resp2.headers = {"Content-Length": str(len(sample_payload))}
        mock_resp2.read.side_effect = [sample_payload, b""]
        mock_resp2.__enter__.return_value = mock_resp2

        mock_opener2 = MagicMock()
        mock_opener2.open.return_value.__enter__.return_value = mock_resp2

        with patch("urllib.request.build_opener", return_value=mock_opener2):
            ok, dest_path = updater.download_installer(info_match)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(dest_path))
            try:
                os.remove(dest_path)
            except Exception:
                pass

    def test_13_check_for_updates_strictly_prefers_setup_over_portable(self):
        """
        Тест 13: Гарантия выбора Inno Setup инсталлятора вместо автономного Portable exe.
        Предотвращает падение автообновления при вызове с ключами /SILENT.
        """
        from updater import GitHubPrivateUpdater
        from unittest.mock import patch, MagicMock
        import json

        updater = GitHubPrivateUpdater(current_version="0.2.0")
        mock_releases = [{
            "tag_name": "v0.3.0",
            "body": "Release notes",
            "assets": [
                {"name": "PowerMaster_ASUS_Portable.exe", "id": 101, "size": 15000000},
                {"name": "PowerMaster_ASUS_Setup.exe", "id": 102, "size": 12000000},
                {"name": "README_INSTALL.txt", "id": 103, "size": 1000},
            ]
        }]

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_releases).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            has_update, rel_info, msg = updater.check_for_updates()
            self.assertTrue(has_update)
            self.assertIsNotNone(rel_info)
            self.assertEqual(rel_info.asset_id, 102)
            self.assertEqual(rel_info.asset_name, "PowerMaster_ASUS_Setup.exe")

    def test_14_extract_sha256_by_asset_name(self):
        """
        Тест 14: Точное сопоставление контрольной суммы SHA-256 по имени ассета в Markdown списке.
        """
        from updater import extract_sha256
        setup_hash = "1111111111111111111111111111111111111111111111111111111111111111"
        portable_hash = "2222222222222222222222222222222222222222222222222222222222222222"

        body = (
            "### 📦 Контрольные суммы (SHA-256):\n"
            f"- **PowerMaster_ASUS_Setup.exe:** `{setup_hash}`\n"
            f"- **PowerMaster_ASUS_Portable.exe:** `{portable_hash}`\n"
        )

        # Выбор для инсталлятора
        self.assertEqual(
            extract_sha256(body, asset_name="PowerMaster_ASUS_Setup.exe"),
            setup_hash
        )
        # Выбор для портативной версии
        self.assertEqual(
            extract_sha256(body, asset_name="PowerMaster_ASUS_Portable.exe"),
            portable_hash
        )

if __name__ == "__main__":
    unittest.main()
