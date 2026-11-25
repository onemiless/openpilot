# Tesla Model 3/Y BMS dashboard

The BMS settings panel replaces Trips. It is a passive subscriber to the existing
`can` service on Vehicle CAN bus 1. It never publishes CAN or sends UDS commands.
It supports the Model 3/Y identifiers used by the Tesla port; other cars display
an unsupported state rather than interpreting unrelated frames.

Displayed telemetry: UI SOC, pack voltage/current/power (positive discharge),
cell thermistor min/max, cell voltage min/max/delta, BMS estimated full capacity,
remaining energy, lifetime charge/discharge counters, instantaneous Wh/km,
vehicle speed/steering/brake, supply warning flags and frame freshness.
Instantaneous Wh/km = pack kW * 1000 / speed km/h, only at >=10 km/h with fresh
battery and vehicle messages. It is not a trip average. Negative values are regen.
No battery-health diagnosis or full DTC scan is inferred from passive telemetry.

## Sources and corrections

Feature reference: https://github.com/hypery11/flipper-tesla-fsd/tree/ffbb24e791a7779499966af28b76c79503ff805c
The GPL project's BMS feature was reviewed; this implementation uses independently
written Python parsing/rendering and CAN signal facts, not its firmware handlers.

Signal cross-check: https://github.com/joshwardell/model3dbc/blob/master/Model3CAN.dbc (MIT)
Multiplexed battery reference: https://github.com/tuncasoftbildik/tesla-can-mod/blob/main/TESLA_CAN_BATTERY_REFERENCE.md
The imported port's `tesla_modely_hw4_perception.dbc` also defines SOCUI at bit 10.

* 0x132: voltage at bit 0, signed current at bit 16. Discharge-positive convention.
* 0x292: use SOCUI bits 10..19, not SOCmin bits 0..9.
* 0x332: mux 0 thermistor extrema, mux 1 cell-voltage extrema. Current recordings
  have incompatible/implausible extrema under the old 0x312 layout, so it is not
  used to display temperature.
* 0x352: mux byte 0 == 0 capacity/remaining-energy fields, 0.02 kWh resolution.
* 0x3D2: lifetime energy counters, 0.001 kWh resolution.
* 0x212: common low-power supply warning bits.
* 0x33A: not decoded as instantaneous consumption; upstream's first-two-byte
  shortcut confuses range-related information with energy consumption.

Invalid ranges/sentinels are withheld. Missing or stale values display a dash
(3 seconds, or 10 seconds for slow energy counters). Opening the panel starts a
bounded passive receive loop; closing drops the socket. No historical values are
silently shown as current when the vehicle sleeps.

## Official Chestnut power path

The dev-sp branch's tinygrad submodule is unchanged at
`fe5d3169ba4f41d0947ad174925f413cbea9d056`, exactly the dependency pinned by the
SP baseline `16322aef167fe14de8af28a9e437101ed3c4dac5`.
`CustomASM24Controller` reads B450, sends USB F3=1 if not L0, and checks again.
This is official Chestnut USB-bridge downstream PCIe power control, not the old
host-PCIe runner. flash.py also matches the baseline. No power code revert was
needed. The old `/data/c3-pcie-runtime/m2_power_enabled` marker remains disabled;
boot uses `launch_chffrplus.sh` with the previously validated road-size option.

Evidence and repeatable scripts: `artifacts/bms-dashboard-20261005/`.
