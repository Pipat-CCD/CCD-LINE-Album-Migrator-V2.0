"""Retain redistribution notices from the installed Python distributions."""
import importlib.metadata
import shutil
import sys
from pathlib import Path

destination = Path(sys.argv[1])
destination.mkdir(parents=True, exist_ok=True)
names = {'license', 'license.txt', 'license.md', 'licence', 'licence.txt', 'copying', 'copyright', 'notice'}
for distribution in importlib.metadata.distributions():
    for relative in distribution.files or []:
        if relative.name.lower() in names or '.dist-info/licenses/' in str(relative).replace('\\', '/'):
            source = distribution.locate_file(relative)
            if source.is_file():
                target = destination / distribution.metadata['Name'] / Path(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.exists():
    shutil.copy2(python_license, destination / 'Python-LICENSE.txt')
