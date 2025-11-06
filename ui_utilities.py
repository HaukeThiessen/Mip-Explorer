# Mip Explorer
#  Copyright (c) Hauke Thiessen
#
#  ---------------------------------------------------------------------------
#
#  This software is provided 'as-is', without any express or implied
#  warranty. In no event will the authors be held liable for any damages
#  arising from the use of this software.
#
#  Permission is granted to anyone to use this software for any purpose,
#  including commercial applications, and to alter it and redistribute it
#  freely, subject to the following restrictions:
#
#  1. The origin of this software must not be misrepresented; you must not
#     claim that you wrote the original software. If you use this software
#     in a product, an acknowledgment in the documentation is be
#     appreciated but not required.
#
#  2. Altered versions must be plainly marked as such, and must not be
#     misrepresented as being the original software.
#
#  3. This notice may not be removed or altered from any source distribution.
#
#  ---------------------------------------------------------------------------


import platform
import subprocess

if platform.system() == "Windows":
    import winreg


def is_system_dark() -> bool:
    if platform.system() == "Darwin":
        try:
            cmd: str = "defaults read -g AppleInterfaceStyle"
            p = subprocess.Popen(cmd, stdout = subprocess.PIPE, stderr = subprocess.PIPE, shell = True)
            return bool(p.communicate()[0])
        except Exception:
            return False
    else:
        if platform.system() == "Windows":
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, "Software/Microsoft/Windows/CurrentVersion/Themes/Personalize"
                )
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return value == 0
            except Exception as e:
                return False
        else:
            return detectDarkModeGnome()


def detectDarkModeGnome():
    '''Detects dark mode in GNOME'''
    getArgs = ['gsettings', 'get', 'org.gnome.desktop.interface', 'gtk-theme']

    currentTheme = subprocess.run(
        getArgs, capture_output=True
    ).stdout.decode("utf-8").strip().strip("'")

    darkIndicator = '-dark'
    if currentTheme.endswith(darkIndicator):
        return True
    return False