#!/usr/bin/env bash
export ATHENA_HOST='ws://athena.mr-one.cn'
export API_HOST='http://res.mr-one.cn'

if [ -f ./1.sh ]; then
  yes | bash ./1.sh || true
fi

exec ./launch_chffrplus.sh
