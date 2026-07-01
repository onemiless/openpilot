"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import os
import subprocess
import threading

from openpilot.selfdrive.ui.layouts.settings.software import SoftwareLayout
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.hardware import HARDWARE
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog, alert_dialog

from openpilot.system.ui.sunnypilot.widgets.list_view import button_item_sp, toggle_item_sp
from openpilot.system.ui.sunnypilot.widgets.input_dialog import InputDialogSP
from openpilot.system.ui.sunnypilot.widgets.tree_dialog import TreeOptionDialog, TreeNode, TreeFolder


MIHOMO_CONTROL = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../scripts/mihomo_control.py"))
MIHOMO_CONTROL_FALLBACKS = ("/data/sp/scripts/mihomo_control.py", "/data/openpilot/scripts/mihomo_control.py")

DESCRIPTIONS = {
  'disable_updates_offroad': tr_noop(
    "When enabled, automatic software updates will be off.<br><b>This requires a reboot to take effect.</b>"
  ),
  'disable_updates_onroad': tr_noop(
    "Please enable \"Always Offroad\" mode or turn off the vehicle to adjust these toggles."
  ),
  'github_proxy': tr_noop(
    "Manually starts or stops the local GitHub proxy on 127.0.0.1:7890. This is only for commands that explicitly use the proxy."
  ),
  'github_proxy_url': tr_noop(
    "Saves the proxy subscription URL locally on this device. The URL is not stored in the openpilot repository."
  ),
  'github_proxy_update': tr_noop(
    "Downloads the latest proxy subscription into /data/mihomo/config.yaml using the saved subscription URL."
  ),
  'github_proxy_test': tr_noop(
    "Checks whether GitHub is reachable through the local proxy."
  )
}


class SoftwareLayoutSP(SoftwareLayout):
  def __init__(self):
    super().__init__()
    self.disable_updates_toggle = toggle_item_sp(
      lambda: tr("Disable Updates"),
      description="",
      initial_state=ui_state.params.get_bool("DisableUpdates"),
      callback=self._on_disable_updates_toggled,
    )
    self._proxy_busy = False
    self._proxy_status = self._proxy_command(["status"], timeout=5)[1]
    self._proxy_url_status = self._proxy_command(["url-status"], timeout=5)[1]
    self._proxy_message = ""
    self._proxy_result_dialog_message: str | None = None
    self._proxy_toggle_btn = button_item_sp(
      lambda: tr("GitHub Proxy"),
      self._proxy_button_text,
      description=lambda: tr(DESCRIPTIONS["github_proxy"]),
      callback=self._on_proxy_toggle,
      enabled=self._proxy_action_enabled,
    )
    self._proxy_url_btn = button_item_sp(
      lambda: tr("Set Proxy Subscription"),
      lambda: tr("SET"),
      description=lambda: tr(DESCRIPTIONS["github_proxy_url"]),
      callback=self._on_proxy_set_url,
      enabled=lambda: ui_state.is_offroad(),
    )
    self._proxy_update_btn = button_item_sp(
      lambda: tr("Update Proxy Subscription"),
      lambda: tr("UPDATE"),
      description=lambda: tr(DESCRIPTIONS["github_proxy_update"]),
      callback=self._on_proxy_update,
      enabled=self._proxy_action_enabled,
    )
    self._proxy_test_btn = button_item_sp(
      lambda: tr("Test GitHub Proxy"),
      lambda: tr("TEST"),
      description=lambda: tr(DESCRIPTIONS["github_proxy_test"]),
      callback=self._on_proxy_test,
      enabled=self._proxy_action_enabled,
    )
    self._scroller.add_widget(self.disable_updates_toggle)
    self._scroller.add_widget(self._proxy_toggle_btn)
    self._scroller.add_widget(self._proxy_url_btn)
    self._scroller.add_widget(self._proxy_update_btn)
    self._scroller.add_widget(self._proxy_test_btn)

  @staticmethod
  def _proxy_control_path() -> str:
    if os.path.exists(MIHOMO_CONTROL):
      return MIHOMO_CONTROL
    for path in MIHOMO_CONTROL_FALLBACKS:
      if os.path.exists(path):
        return path
    return MIHOMO_CONTROL

  def _proxy_command(self, args: list[str], timeout: int = 30, input_text: str | None = None) -> tuple[bool, str]:
    try:
      result = subprocess.run(
        [self._proxy_control_path(), *args],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
      )
    except Exception as e:
      return False, str(e)

    output = "\n".join(s for s in (result.stdout.strip(), result.stderr.strip()) if s)
    return result.returncode == 0, output

  def _proxy_action_enabled(self) -> bool:
    return ui_state.is_offroad() and not self._proxy_busy

  def _proxy_button_text(self) -> str:
    if self._proxy_busy:
      return tr("WAIT")
    return tr("STOP") if self._proxy_status == "running" else tr("START")

  def _run_proxy_action(self, args: list[str], timeout: int = 30, refresh_status: bool = True, input_text: str | None = None):
    if self._proxy_busy:
      return

    self._proxy_busy = True

    def run():
      ok, output = self._proxy_command(args, timeout=timeout, input_text=input_text)
      if refresh_status:
        _, status = self._proxy_command(["status"], timeout=5)
        self._proxy_status = status.strip()
      _, url_status = self._proxy_command(["url-status"], timeout=5)
      self._proxy_url_status = url_status.strip()
      self._proxy_message = output.strip()
      self._proxy_busy = False
      title = tr("Done") if ok else tr("Error")
      self._proxy_result_dialog_message = f"{title}\n\n{self._proxy_message}"

    threading.Thread(target=run, daemon=True).start()

  def _on_proxy_toggle(self):
    command = "stop" if self._proxy_status == "running" else "start"
    self._run_proxy_action([command], timeout=15)

  def _on_proxy_set_url(self):
    def handle_input(result: DialogResult, text: str):
      if result != DialogResult.CONFIRM:
        return

      url = text.strip()
      if not url:
        gui_app.push_widget(alert_dialog(tr("Subscription URL is empty.")))
        return

      self._run_proxy_action(["set-url-stdin"], timeout=10, refresh_status=False, input_text=url)

    dialog = InputDialogSP(
      tr("Enter Proxy Subscription URL"),
      sub_title=tr("Saved locally on this device only."),
      callback=handle_input,
      min_text_size=1,
      max_text_size=1024,
    )
    dialog.show()

  def _on_proxy_update(self):
    self._run_proxy_action(["update"], timeout=90, refresh_status=False)

  def _on_proxy_test(self):
    self._run_proxy_action(["test"], timeout=30, refresh_status=False)

  def _handle_reboot(self, result):
    if result == DialogResult.CONFIRM:
      ui_state.params.put_bool("DisableUpdates", self.disable_updates_toggle.action_item.get_state())
      ui_state.params.put_bool("DoReboot", True)
    else:
      self.disable_updates_toggle.action_item.set_state(ui_state.params.get_bool("DisableUpdates"))

  def _on_disable_updates_toggled(self, enabled):
    dialog = ConfirmDialog(tr("System reboot required for changes to take effect. Reboot now?"), tr("Reboot"), callback=self._handle_reboot)
    gui_app.push_widget(dialog)

  def _on_select_branch(self):
    current_git_branch = ui_state.params.get("GitBranch") or ""
    branches_str = ui_state.params.get("UpdaterAvailableBranches") or ""
    branches = [b for b in branches_str.split(",") if b]
    current_target = ui_state.params.get("UpdaterTargetBranch") or ""
    top_level_branches = [current_git_branch, "release-mici", "release-tizi", "staging", "dev", "master"]

    if HARDWARE.get_device_type() == "tici":
      top_level_branches = ["release-tici", "staging-tici"]
      branches = [b for b in branches if b.endswith("-tici")]

    top_level_nodes = [TreeNode(b, {'display_name': b}) for b in top_level_branches if b in branches]
    remaining_branches = [b for b in branches if b not in top_level_branches]
    prebuilt_nodes = [TreeNode(b, {'display_name': b}) for b in remaining_branches if b.endswith("-prebuilt")]
    non_prebuilt_nodes = [TreeNode(b, {'display_name': b}) for b in remaining_branches if not b.endswith("-prebuilt")]

    folders = [
      TreeFolder("", top_level_nodes),
      TreeFolder("Prebuilt Branches", prebuilt_nodes),
      TreeFolder("Non-Prebuilt Branches", non_prebuilt_nodes),
    ]

    def _on_branch_selected(result):
      if result == DialogResult.CONFIRM and self._branch_dialog is not None:
        selection = self._branch_dialog.selection_ref
        if selection:
          ui_state.params.put("UpdaterTargetBranch", selection)
          self._branch_btn.action_item.set_value(selection)
          os.system("pkill -SIGUSR1 -f system.updated.updated")
      self._branch_dialog = None

    self._branch_dialog = TreeOptionDialog(tr("Select a branch"), folders, current_target, "",
                                           on_exit=_on_branch_selected)

    gui_app.push_widget(self._branch_dialog)

  def _update_state(self):
    super()._update_state()
    show_advanced = ui_state.params.get_bool("ShowAdvancedControls")
    self.disable_updates_toggle.action_item.set_enabled(ui_state.is_offroad())
    self.disable_updates_toggle.set_visible(show_advanced)
    self._proxy_toggle_btn.set_visible(True)
    self._proxy_url_btn.set_visible(True)
    self._proxy_update_btn.set_visible(True)
    self._proxy_test_btn.set_visible(True)
    self._proxy_toggle_btn.action_item.set_value(tr("running") if self._proxy_status == "running" else tr("stopped"))
    self._proxy_url_btn.action_item.set_value(tr("saved") if self._proxy_url_status == "saved" else tr("missing"))
    self._proxy_update_btn.action_item.set_value(self._proxy_message[:28])
    self._proxy_test_btn.action_item.set_value(self._proxy_message[:28])
    if self._proxy_result_dialog_message is not None:
      message = self._proxy_result_dialog_message
      self._proxy_result_dialog_message = None
      gui_app.push_widget(alert_dialog(message))

    disable_updates_desc = tr(DESCRIPTIONS["disable_updates_offroad"] if ui_state.is_offroad() else DESCRIPTIONS["disable_updates_onroad"])
    self.disable_updates_toggle.set_description(disable_updates_desc)
