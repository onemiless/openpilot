import os
import tempfile
from uuid import uuid4

import pytest

from openpilot.common.utils import atomic_write


class TestFileHelpers:
  def run_atomic_write_func(self, atomic_write_func):
    path = f"/tmp/tmp{uuid4()}"
    with atomic_write_func(path) as f:
      f.write("test")
      assert not os.path.exists(path)

    with open(path) as f:
      assert f.read() == "test"
    os.remove(path)

  def test_atomic_write(self):
    self.run_atomic_write_func(atomic_write)

  def test_atomic_write_cleans_up_after_failure(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
      path = os.path.join(tmp_dir, "target")
      with pytest.raises(RuntimeError):
        with atomic_write(path) as f:
          f.write("partial")
          raise RuntimeError("write failed")

      assert not os.path.exists(path)
      assert os.listdir(tmp_dir) == []
