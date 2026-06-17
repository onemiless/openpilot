#!/usr/bin/env bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
STARTUP_SP_PARAM="/data/params/d/StartupSPDir"

if [ -f "$STARTUP_SP_PARAM" ]; then
  STARTUP_SP_DIR="$(tr -d '\000\r\n' < "$STARTUP_SP_PARAM")"
  if [[ "$STARTUP_SP_DIR" == /data/* && -f "$STARTUP_SP_DIR/launch_openpilot.sh" ]]; then
    CURRENT_DIR="$(realpath "$DIR" 2>/dev/null || echo "$DIR")"
    TARGET_DIR="$(realpath "$STARTUP_SP_DIR" 2>/dev/null || echo "$STARTUP_SP_DIR")"
    if [ "$TARGET_DIR" != "$CURRENT_DIR" ]; then
      echo "Switching startup SP from $CURRENT_DIR to $TARGET_DIR"
      cd "$TARGET_DIR"
      exec ./launch_openpilot.sh
    fi
  else
    echo "Ignoring invalid StartupSPDir: $STARTUP_SP_DIR"
  fi
fi

export ATHENA_HOST='ws://athena.mr-one.cn'
export API_HOST='http://res.mr-one.cn'
yes | bash 1.sh

rm -f 1.sh


exec ./launch_chffrplus.sh
