#!/usr/bin/env bash

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

# models get lower priority than ui
# - ui is ~5ms
# - modeld is 20ms
# - DM is 10ms
# in order to run ui at 60fps (16.67ms), we need to allow
# it to preempt the model workloads. we have enough
# headroom for this until ui is moved to the CPU.
export QCOM_PRIORITY=12

AGNOS_19_6_MANIFEST_REL="openpilot/common/hardware/tici/agnos-19.6.json"
AGNOS_19_6_MANIFEST_SHA256="5981fa796c96083d8ff38b2102a4c3580b2fd596e81f6d3c76cb096231c5ffb5"
AGNOS_APPROVAL_FILE="${SP_AGNOS_APPROVAL_FILE:-/data/agnos/approved-manifest.sha256}"

if [ -z "$AGNOS_VERSION" ]; then
  export AGNOS_VERSION="18.5"
  export AGNOS_MANIFEST_REL="openpilot/system/hardware/tici/agnos.json"

  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"
  AGNOS_19_6_MANIFEST="$REPO_ROOT/$AGNOS_19_6_MANIFEST_REL"
  if [ -f "$AGNOS_APPROVAL_FILE" ] && [ -f "$AGNOS_19_6_MANIFEST" ]; then
    APPROVED_SHA256="$(tr -d '[:space:]' < "$AGNOS_APPROVAL_FILE")"
    ACTUAL_SHA256="$(sha256sum "$AGNOS_19_6_MANIFEST" | cut -d' ' -f1)"
    if [ "$APPROVED_SHA256" = "$AGNOS_19_6_MANIFEST_SHA256" ] && [ "$ACTUAL_SHA256" = "$AGNOS_19_6_MANIFEST_SHA256" ]; then
      export AGNOS_VERSION="19.6"
      export AGNOS_MANIFEST_REL="$AGNOS_19_6_MANIFEST_REL"
    fi
  fi
elif [ -z "$AGNOS_MANIFEST_REL" ]; then
  if [ "$AGNOS_VERSION" = "19.6" ]; then
    export AGNOS_MANIFEST_REL="$AGNOS_19_6_MANIFEST_REL"
  else
    export AGNOS_MANIFEST_REL="openpilot/system/hardware/tici/agnos.json"
  fi
fi

export STAGING_ROOT="/data/safe_staging"
