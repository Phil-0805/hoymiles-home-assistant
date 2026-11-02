"""Cross-check a synthetic fixture against a pinned, external Node-RED decoder.

No Hoymiles connection, account credentials or device commands are involved.
The optional network request downloads only the reviewed public JS source.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.request import urlopen

URL = "https://raw.githubusercontent.com/pinguin45orga/node-red-contrib-hoymiles-home/e48ac860e2d1d17fdad108be4dfe306e511608e2/nodes/hoymiles-modules/module-data.js"
SHA256 = "6f249de5cf0f6dcbfe2fe959c1e1d2197de1aa4d45d4fe0f4141a6e47ab1c67d"
CHECK = """
const fs = require('fs');
const f = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const d = require(process.argv[1]).decodeModuleData(Buffer.from(f.raw_base64, 'base64'));
const m = d.micros[f.expected.device_id], i = m.time.length - 1;
if (d.sid !== f.station_id || d.date !== f.date || m.time[i] !== f.expected.time) throw Error('Identity/time mismatch');
for (const [key, values] of Object.entries({temperature:m.pn_temp, frequency:m.pn_hz, voltage:m.pn_u_a})) {
  if (Math.abs(values[i] - f.expected[key]) > 0.001) throw Error(key + ' mismatch');
}
console.log('Pinned Node-RED decoder matches the synthetic module fixture. No cloud calls were made.');
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-file", type=Path, help="Use a local copy for a fully offline check")
    args = parser.parse_args()
    source = args.reference_file.read_bytes() if args.reference_file else urlopen(URL, timeout=20).read()
    # Normalize the final newline only; the reviewed source must otherwise match.
    source = source.rstrip(b"\r\n") + b"\n"
    if hashlib.sha256(source).hexdigest() != SHA256:
        raise SystemExit("Reference checksum mismatch; refusing to execute it")
    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/module_snapshot.json"
    json.loads(fixture.read_text())
    with tempfile.TemporaryDirectory() as directory:
        reference = Path(directory) / "module-data.cjs"
        reference.write_bytes(source)
        subprocess.run(["node", "-e", CHECK, str(reference), str(fixture)], check=True, timeout=10)


if __name__ == "__main__":
    main()
