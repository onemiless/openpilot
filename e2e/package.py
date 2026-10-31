"""Verify shipped assets and model metadata without constructing a GPU or loading weights."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from model_loader import read_parts, _MetadataUnpickler
import io
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'assets.json').read_text())
for name,digest in manifest['sha256'].items():
  with (root/name).open('rb') as source: assert hashlib.file_digest(source,'sha256').hexdigest()==digest,name
assert not (root/'.gitmodules').exists()
assert not list(root.rglob('.gitmodules'))
assert not any(p.name=='.git' for p in (root/'tinygrad').rglob('*'))
assert not (root/'openpilot').exists() and not (root/'panda').exists()
for name in ('launch_openpilot.sh','launch_chffrplus.sh'):
  source=(root/name).read_text()
  assert not any(term in source for term in ('AGNOS','/VERSION','agnos_init','manager.py','pip ','reboot','git pull'))
assert len(list((root/'models').iterdir()))==1
parts,extra=read_parts(str(root/'models/big_driving_tinygrad.pkl'))
assert list(parts)==['run']
assert extra['input_specs']['new_img'][0]==(2,6,128,256)
assert all(spec[2]=='AMD' for spec in (*extra['input_specs'].values(),*extra['output_specs'].values()))
slices=_MetadataUnpickler(io.BytesIO(base64.b64decode(extra['metadata']['metadata']['output_slices']))).load()
assert slices['plan'].stop>slices['plan'].start
fw=ast.literal_eval(ast.parse((root/'tinygrad/runtime/autogen/am/fw.py').read_text()).body[0].value)
assert all(hashlib.sha256((root/'firmware/amdgpu'/name).read_bytes()).hexdigest()==digest for name,digest in fw.items())
report={'status':'PASS','scope':'package integrity + actual official model metadata; no USB/GPU',
        'files_checked':len(manifest['sha256']),'model':json.loads((root/'provenance.json').read_text())['official_model']['bundle']['display_name'],
        'input_specs':extra['input_specs'],'output_specs':extra['output_specs'],'gpu_firmware_count':len(fw),
        'assets_manifest_sha256':hashlib.sha256((root/'assets.json').read_bytes()).hexdigest()}
output=Path(sys.argv[1]);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
print('PASS package/model metadata:',output)
