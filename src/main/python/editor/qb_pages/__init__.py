# SPDX-License-Identifier: GPL-2.0-or-later
"""Editor pages for the settings behind QuickBuild keys. Each page is a QWidget
with set_app_config(app_config_or_None) and shown()."""

from editor.qb_pages.keysplit_page import KeySplitPage
from editor.qb_pages.drumlive_page import DrumLivePage
from editor.qb_pages.rhythm_page import RhythmEnginePage
from editor.qb_pages.drum_machine_page import DrumMachinePage
from editor.qb_pages.autofader_page import AutoFaderPage
from editor.qb_pages.smartchord_page import SmartChordPage, VoiceLeadingPage

__all__ = ["KeySplitPage", "DrumLivePage", "RhythmEnginePage", "DrumMachinePage", "AutoFaderPage",
           "SmartChordPage", "VoiceLeadingPage"]
