import sys
import unittest.mock
import ctypes

if sys.platform != "win32" or not hasattr(ctypes, "windll"):
    ctypes.windll = unittest.mock.MagicMock()

import unittest
import test_updater_and_icons
import test_settings_and_tray
import test_powermaster
import test_dashboard

if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromModule(test_updater_and_icons))
    suite.addTests(loader.loadTestsFromModule(test_settings_and_tray))
    suite.addTests(loader.loadTestsFromModule(test_powermaster))
    suite.addTests(loader.loadTestsFromModule(test_dashboard))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(not result.wasSuccessful())
