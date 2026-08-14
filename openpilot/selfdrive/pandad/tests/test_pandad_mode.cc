#include "selfdrive/pandad/pandad_mode.h"

constexpr PandaRuntimeMode parked = get_panda_runtime_mode(false, false, false);
static_assert(!parked.ignition);
static_assert(parked.power_save);
static_assert(parked.no_output);

constexpr PandaRuntimeMode settings = get_panda_runtime_mode(true, false, false);
static_assert(settings.ignition);
static_assert(!settings.power_save);
static_assert(settings.no_output);

constexpr PandaRuntimeMode driving = get_panda_runtime_mode(false, true, true);
static_assert(driving.ignition);
static_assert(!driving.power_save);
static_assert(!driving.no_output);

int main() {}
