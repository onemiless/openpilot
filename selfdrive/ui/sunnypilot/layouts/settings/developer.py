"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import datetime
import os
from pathlib import Path

from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.layouts.settings.developer import DeveloperLayout
from openpilot.system.hardware import PC
from openpilot.system.hardware.hw import Paths
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.widgets.list_view import button_item

from openpilot.sunnypilot.selfdrive.selfdrived.tesla_mads_debug import TESLA_MADS_DEBUG_PATH, clear_tesla_mads_debug_logs
from openpilot.system.ui.sunnypilot.widgets.html_render import HtmlModalSP
from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp

PREBUILT_PATH = os.path.join(Paths.comma_home(), "prebuilt") if PC else "/data/openpilot/prebuilt"


class DeveloperLayoutSP(DeveloperLayout):
  def __init__(self):
    super().__init__()
    self.error_log_path = os.path.join(Paths.crash_log_root(), "error.log")
    self._is_release_branch: bool = self._is_release or ui_state.params.get_bool("IsReleaseSpBranch")
    self._is_development_branch: bool = ui_state.params.get_bool("IsTestedBranch") or ui_state.params.get_bool("IsDevelopmentBranch")
    self._initialize_items()

    for item in self.items:
      self._scroller.add_widget(item)

  def _initialize_items(self):
    self.show_advanced_controls = toggle_item_sp(tr("Show Advanced Controls"),
                                                 tr("Toggle visibility of advanced sunnypilot controls.<br>This only changes the visibility of the toggles; " +
                                                    "it does not change the actual enabled/disabled state."), param="ShowAdvancedControls")

    self.enable_github_runner_toggle = toggle_item_sp(tr("GitHub Runner Service"), tr("Enables or disables the GitHub runner service."),
                                                      param="EnableGithubRunner")

    self.enable_copyparty_toggle = toggle_item_sp(tr("copyparty Service"),
                                                  tr("copyparty is a very capable file server, you can use it to download your routes, view your logs " +
                                                     "and even make some edits on some files from your browser. " +
                                                     "Requires you to connect to your comma locally via its IP address."), param="EnableCopyparty")

    self.prebuilt_toggle = toggle_item_sp(tr("Quickboot Mode"), "", param="QuickBootToggle", callback=self._on_prebuilt_toggled)

    self.error_log_btn = button_item(tr("Error Log"), tr("VIEW"), tr("View the error log for sunnypilot crashes."), callback=self._on_error_log_clicked)
    self.tesla_mads_log_btn = button_item(tr("Tesla MADS Debug Log"), tr("CLEAR"),
                                          tr("Clear the Tesla MADS diagnostic log used for stock longitudinal/MADS handoff debugging."),
                                          callback=self._on_tesla_mads_log_clear_clicked)
    self.offline_wake_success_btn = button_item(tr("Offline Wake Success"), tr("CLEAR"),
                                                tr("Clear the panda latched offline wake success record so the next successful wake can be captured."),
                                                callback=self._on_offline_wake_success_clear_clicked)
    self.panda_bootkick_test_btn = button_item(tr("Panda Bootkick Test"), tr("TEST"),
                                               tr("Schedule a panda bootkick in 90 seconds and power off the device to test whether panda can wake the SoM."),
                                               callback=self._on_panda_bootkick_test_clicked)

    self.items: list = [self.show_advanced_controls, self.enable_github_runner_toggle, self.enable_copyparty_toggle,
                        self.prebuilt_toggle, self.offline_wake_success_btn, self.panda_bootkick_test_btn,
                        self.tesla_mads_log_btn, self.error_log_btn,]

  @staticmethod
  def _on_prebuilt_toggled(state):
    if state:
      Path(PREBUILT_PATH).touch(exist_ok=True)
    else:
      os.remove(PREBUILT_PATH)
    ui_state.params.put_bool("QuickBootToggle", state)

  def _on_delete_confirm(self, result):
    if result == DialogResult.CONFIRM:
      if os.path.exists(self.error_log_path):
        os.remove(self.error_log_path)

  def _on_error_log_closed(self, result, log_exists):
    if result == DialogResult.CONFIRM and log_exists:
      dialog2 = ConfirmDialog(tr("Would you like to delete this log?"), tr("Yes"), tr("No"), rich=False, callback=self._on_delete_confirm)
      gui_app.push_widget(dialog2)

  def _on_error_log_clicked(self):
    text = ""
    if os.path.exists(self.error_log_path):
      text = f"<b>{datetime.datetime.fromtimestamp(os.path.getmtime(self.error_log_path)).strftime('%d-%b-%Y %H:%M:%S').upper()}</b><br><br>"
      try:
        with open(self.error_log_path) as file:
          text += file.read()
      except Exception:
        pass
    dialog = HtmlModalSP(text=text, callback=lambda result: self._on_error_log_closed(result, os.path.exists(self.error_log_path)))
    gui_app.push_widget(dialog)

  def _on_tesla_mads_log_clear_confirm(self, result):
    if result == DialogResult.CONFIRM:
      clear_tesla_mads_debug_logs()

  def _on_tesla_mads_log_clear_clicked(self):
    log_size = 0
    for path in (TESLA_MADS_DEBUG_PATH, f"{TESLA_MADS_DEBUG_PATH}.1"):
      try:
        log_size += os.path.getsize(path)
      except OSError:
        pass

    size_kb = log_size / 1024
    message = tr("Clear Tesla MADS debug log?") + f"<br><br>{TESLA_MADS_DEBUG_PATH}<br>{size_kb:.1f} KB"
    dialog = ConfirmDialog(message, tr("Clear"), tr("Cancel"), rich=True, callback=self._on_tesla_mads_log_clear_confirm)
    gui_app.push_widget(dialog)

  def _on_offline_wake_success_clear_confirm(self, result):
    if result != DialogResult.CONFIRM:
      return

    cleared = 0
    errors = []
    try:
      from panda import Panda
      for serial in Panda.list():
        try:
          with Panda(serial) as panda:
            panda.clear_wake_success()
            cleared += 1
        except Exception as e:
          errors.append(f"{serial}: {type(e).__name__}: {e}")
    except Exception as e:
      errors.append(f"Panda.list: {type(e).__name__}: {e}")

    try:
      with open("/data/offline_wake_debug.log", "a") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ui cleared offline wake success cleared={cleared} errors={errors}\n")
    except Exception:
      pass

  def _on_offline_wake_success_clear_clicked(self):
    message = tr("Clear panda offline wake success record?") + "<br><br>" + tr("The next successful offline wake will be captured after clearing.")
    dialog = ConfirmDialog(message, tr("Clear"), tr("Cancel"), rich=True, callback=self._on_offline_wake_success_clear_confirm)
    gui_app.push_widget(dialog)

  @staticmethod
  def _on_panda_bootkick_test_confirm(result):
    if result != DialogResult.CONFIRM:
      return

    scheduled = 0
    errors = []
    delay_s = 90
    try:
      from panda import Panda
      for serial in Panda.list():
        try:
          with Panda(serial) as panda:
            if not panda.is_internal():
              continue
            panda.clear_wake_success()
            panda.schedule_bootkick_test(delay_s)
            scheduled += 1
        except Exception as e:
          errors.append(f"{serial}: {type(e).__name__}: {e}")
    except Exception as e:
      errors.append(f"Panda.list: {type(e).__name__}: {e}")

    try:
      with open("/data/offline_wake_debug.log", "a") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ui scheduled panda bootkick test delay_s={delay_s} scheduled={scheduled} errors={errors}\n")
    except Exception:
      pass

    if scheduled > 0:
      ui_state.params.put_bool("DoShutdown", True)

  def _on_panda_bootkick_test_clicked(self):
    message = (
      tr("Run panda bootkick self-test?") + "<br><br>" +
      tr("The device will power off now. If panda can wake the SoM, it should boot again in about 90 seconds.")
    )
    dialog = ConfirmDialog(message, tr("Test"), tr("Cancel"), rich=True, callback=self._on_panda_bootkick_test_confirm)
    gui_app.push_widget(dialog)

  def _update_state(self):
    disable_updates = ui_state.params.get_bool("DisableUpdates")
    show_advanced = ui_state.params.get_bool("ShowAdvancedControls")

    if (prebuilt_file := os.path.exists(PREBUILT_PATH)) != ui_state.params.get_bool("QuickBootToggle"):
      ui_state.params.put_bool("QuickBootToggle", prebuilt_file)
      self.prebuilt_toggle.action_item.set_state(prebuilt_file)

    self.prebuilt_toggle.set_visible(show_advanced and not (self._is_release_branch or self._is_development_branch))
    self.prebuilt_toggle.action_item.set_enabled(disable_updates)

    if disable_updates:
      self.prebuilt_toggle.set_description(tr("When toggled on, this creates a prebuilt file to allow accelerated boot times. When toggled off, it " +
                                              "removes the prebuilt file so compilation of locally edited cpp files can be made."))
    else:
      self.prebuilt_toggle.set_description(tr("Quickboot mode requires updates to be disabled.<br>Enable 'Disable Updates' in the Software panel first."))

    self.enable_copyparty_toggle.set_visible(show_advanced)
    self.enable_github_runner_toggle.set_visible(show_advanced and not self._is_release_branch)
    self.offline_wake_success_btn.set_visible(not self._is_release_branch)
    self.panda_bootkick_test_btn.set_visible(not self._is_release_branch)
    self.tesla_mads_log_btn.set_visible(not self._is_release_branch)
    self.error_log_btn.set_visible(not self._is_release_branch)
