# sp-flasher

Only R2 automatic flashing, verification and 60-second big-model inference belong here.
No driving stack, system version gate or system updater. Dependencies are ordinary folders, never submodules.
Never access/flash a device during host development. Device validation requires a separate explicit request.
Write failure scenarios and E2E coverage before implementation; do not add unit tests after code.
Commit coherent work on sp-flasher. Preserve verifiable artifacts and distinguish host simulation from hardware proof.
