"""Full disclosure: https://ankiweb.net/shared/info/1133851639 was used as a
base. I tried using it myself at first but noticed several problems including
the deprecated RPC library. The main problem was that the add-on/repository had
not been updated to fix these issues for more than half a year. So I decided to
(hopefully) fix all the issues and improve the add-on overall as well as keep
updating it if anything pops up"""

# pylint: disable=broad-except

import time
import os
from typing import Union
from anki.hooks import addHook
from aqt import mw
from .pypresence import presence as pp


class Ankicord():
    """Ankicord class"""

    def __init__(self):
        self.due_message = "   "
        self.deck_name = ""
        self.skip_edit = False

        self.start_time = round(time.time())
        self.curr_time = round(time.time()) - 15

        self.connected = False
        self.client_id = '745326655395856514'
        self.rpc = pp.Presence(self.client_id)

        self.config = self.__get_resolved_config()

    def __get_resolved_config(self,
                              cfg: Union[dict, list] = None) -> Union[dict, list]:
        """Translate config (e.g. 'on' -> True)"""
        if cfg is None:
            cfg = mw.addonManager.getConfig(__name__)['defaults']
        table = {
            "on": True,
            "off": False
        }

        config_keys = None
        if isinstance(cfg, dict):
            cfg = dict(cfg)
            config_keys = cfg.keys()
        elif isinstance(cfg, list):
            cfg = list(cfg)
            config_keys = range(len(cfg))

        for k in config_keys:
            if isinstance(cfg[k], (dict, list)):
                cfg[k] = self.__get_resolved_config(cfg[k])
            elif isinstance(cfg[k], str) and cfg[k] in table:
                cfg[k] = table[cfg[k]]
        return cfg

    def connect_rpc(self):
        """Connect to the Discord Rich Presence"""
        try:
            self.rpc.connect()
            self.connected = True
        except Exception as ex:
            print(ex)

    @staticmethod
    def __get_spotify_info() -> str:
        """Get currently active Spotify track info. LINUX ONLY"""
        try:
            player_status_cmd = "gdbus call --session --dest org.mpris.MediaPlayer2.spotify \
                --object-path /org/mpris/MediaPlayer2 --method org.freedesktop.DBus.Properties.Get \
                org.mpris.MediaPlayer2.Player PlaybackStatus | cut -d \"'\" -f 2"
            track_cmd = "dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify \
                /org/mpris/MediaPlayer2 org.freedesktop.DBus.Properties.Get \
                string:org.mpris.MediaPlayer2.Player string:Metadata | sed -n '/title/{n;p}' | \
                cut -d '\"' -f 2"
            artist_cmd = "dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify \
                /org/mpris/MediaPlayer2 org.freedesktop.DBus.Properties.Get \
                string:org.mpris.MediaPlayer2.Player string:Metadata | sed -n '/artist/{n;n;p}' | \
                cut -d '\"' -f 2"

            stream = os.popen(player_status_cmd)
            player_status = stream.read().strip()

            if player_status == "Playing":
                stream = os.popen(artist_cmd)
                artist = stream.read().strip()

                stream = os.popen(track_cmd)
                track = stream.read().strip()

                return artist + " ー " + track

            return None
        except Exception as ex:
            print(ex)
            return None

    def get_config_val(self, cfg_key, cfg_type):
        """Check if key in config exists. If it does, get value, if not - None"""
        cfg_val = self.config.get(cfg_key, None)
        if isinstance(cfg_val, cfg_type):
            return cfg_val
        return None

    def rpc_update(self, details_message) -> None:
        """Updates the Discord Rich Presence with provided details_message"""
        try:
            if not self.connected:
                self.connect_rpc()

            # update Rich Presence
            if round(time.time()) - 15 > curr_time:
                #! Spotify (LINUX ONLY)
                if self.get_config_val('spotify', bool):
                    spotify_info = self.__get_spotify_info()
                    if spotify_info is not None:
                        self.rpc.update(details=details_message,
                                        state=self.due_message,
                                        large_image="anki",
                                        small_image="spotify",
                                        small_text=spotify_info,
                                        start=self.start_time)
                    else:
                        self.rpc.update(details=details_message,
                                        state=self.due_message,
                                        large_image="anki",
                                        start=self.start_time)
                else:
                    self.rpc.update(details=details_message,
                                    state=self.due_message,
                                    large_image="anki",
                                    start=self.start_time)
                curr_time = round(time.time())
        except Exception as ex:
            self.connected = False
            print(ex)

    def update_due_message(self) -> None:
        """Calculate reviews due"""
        due_count = 0

        for i in mw.col.sched.deckDueTree():  # TODO: deprecated
            _name, _did, due, lrn, new, _children = i
            due_count += due + lrn + new

        # Correct for single or no cards
        if due_count == 0:
            self.due_message = str(self.config['no_cards_left_txt'])
        elif due_count == 1:
            self.due_message = "(" + str(due_count) + " card left)"
        else:
            self.due_message = "(" + str(due_count) + " cards left)"

    def on_state(self, state, _old_state):
        """Take current state and old_state from hook. If browsing, skip
        'edit' hook. Call update"""
        if self.get_config_val('card_count', bool):
            self.update_due_message()

        if not self.get_config_val('activity', bool):
            self.rpc_update("   ")
            return

        if state == "deckBrowser":
            self.rpc_update(self.get_config_val('menu_status', str))

        elif state == "review":
            reviews_msg = self.get_config_val('reviewing_status', str)
            if self.get_config_val('show_deck', bool) and self.deck_name != "":
                reviews_msg += " [" + self.deck_name + "]"
            self.rpc_update(reviews_msg)

        elif state == "browse":
            self.skip_edit = True
            self.rpc_update(self.get_config_val('browsing_status', str))

        elif state == "edit":
            self.rpc_update(self.get_config_val('editing_status', str))

    def on_browse(self, _x):
        """Handle browse state"""
        self.on_state("browse", "dummy")

    def on_editor(self, _x, _y):
        """Handle editor state if not in browser"""
        if not self.skip_edit:
            self.on_state("edit", "dummy")

        self.skip_edit = False

    def on_answer(self):
        """Handle review state"""
        self.deck_name = str(mw.col.decks.get(mw.reviewer.card.did)['name'])
        self.on_state("review", "dummy")


ac = Ankicord()

if not ac.get_config_val('timer', bool):
    ac.start_time = None

if ac.get_config_val('activity', bool):
    ac.rpc_update(ac.get_config_val('menu_status', str))
else:
    ac.rpc_update("   ")


addHook("afterStateChange", ac.on_state)
addHook("browser.setupMenus", ac.on_browse)
addHook("setupEditorShortcuts", ac.on_editor)
addHook("showAnswer", ac.on_answer)
