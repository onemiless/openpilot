import os

from openpilot.common.swaglog import SwaglogRotatingFileHandler


def test_rollover_deletes_oldest_file(tmp_path):
  base_filename = os.path.join(tmp_path, "swaglog")
  for index in range(3):
    with open(f"{base_filename}.{index:010}", "w") as f:
      f.write(str(index))

  handler = SwaglogRotatingFileHandler(base_filename, backup_count=3)
  handler.close()

  assert not os.path.exists(f"{base_filename}.0000000000")
  assert os.path.exists(f"{base_filename}.0000000001")
  assert os.path.exists(f"{base_filename}.0000000002")
  assert os.path.exists(f"{base_filename}.0000000003")
