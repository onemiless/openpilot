#pragma once

struct PandaRuntimeMode {
  bool ignition;
  bool power_save;
  bool no_output;
};

constexpr PandaRuntimeMode get_panda_runtime_mode(bool ignition_line, bool ignition_can, bool is_onroad) {
  const bool ignition = ignition_line || ignition_can;
  return {ignition, !ignition, !ignition || !is_onroad};
}
