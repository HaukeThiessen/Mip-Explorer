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


import core
import json
import os


class Settings:
    color_affixes:    list[str] = []
    data_affixes:     list[str] = []
    channels_affixes: list[str] = []
    normal_affixes:   list[str] = []
    use_automatic_texture_type = False

    current_texture_type: core.TextureType = core.TextureType.COLOR
    current_directory = ""

    settings_path: str = os.path.dirname(__file__) + "\\Saved\\Settings.json"

    @staticmethod
    def load_settings():
        try:
            with open(Settings.settings_path) as f:
                data = json.load(f)
            if "color_affixes" in data:
                Settings.color_affixes = data["color_affixes"]
            if "data_affixes" in data:
                Settings.data_affixes = data["data_affixes"]
            if "channels_affixes" in data:
                Settings.channels_affixes = data["channels_affixes"]
            if "normal_affixes" in data:
                Settings.normal_affixes = data["normal_affixes"]
            if "use_automatic_texture_type" in data:
                Settings.use_automatic_texture_type = data["use_automatic_texture_type"]
            if "current_directory" in data:
                Settings.current_directory = data["current_directory"]
            if "current_texture_type" in data:
                Settings.current_texture_type = core.TextureType(data["current_texture_type"])
        except:
            print("No saved settings found. Using default settings")

    @staticmethod
    def save_settings():
        dir_saved = os.path.dirname(Settings.settings_path)
        if not os.path.exists(dir_saved):
            try:
                os.mkdir(dir_saved)
            except:
                print("Failed to create the Saved directory")
        try:
            with open(Settings.settings_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "color_affixes":          Settings.color_affixes,
                        "data_affixes":           Settings.data_affixes,
                        "channels_affixes":       Settings.channels_affixes,
                        "normal_affixes":         Settings.normal_affixes,
                        "use_automatic_texture_type":Settings.use_automatic_texture_type,
                        "current_directory":      Settings.current_directory,
                        "current_texture_type":      Settings.current_texture_type.value
                    },
                    f,
                    ensure_ascii = False,
                    indent = 4,
                )
        except:
            print("Failed to write settings to file")

    @staticmethod
    def get_automatic_texture_type(filePath: str) -> core.TextureType:
        if Settings.use_automatic_texture_type == False:
            return core.TextureType.MAX

        base_name = os.path.splitext(os.path.basename(filePath))[0]
        if any(base_name.endswith(affix) for affix in Settings.color_affixes)     or any(base_name.startswith(affix) for affix in Settings.color_affixes):
            return core.TextureType.COLOR
        if any(base_name.endswith(affix) for affix in Settings.data_affixes)      or any(base_name.startswith(affix) for affix in Settings.data_affixes):
            return core.TextureType.DATA
        if any(base_name.endswith(affix) for affix in Settings.channels_affixes)  or any(base_name.startswith(affix) for affix in Settings.channels_affixes):
            return core.TextureType.CHANNELS
        if any(base_name.endswith(affix) for affix in Settings.normal_affixes)    or any(base_name.startswith(affix) for affix in Settings.normal_affixes):
            return core.TextureType.NORMAL
        return core.TextureType.MAX