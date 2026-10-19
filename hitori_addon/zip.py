import zipfile
from collections.abc import Mapping
from pathlib import Path


def create_zip(
    zip_file_path: str | Path,
    file_arcname_map: Mapping[str | Path | bytes, str | Path],
):
    with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_or_content, arcname in file_arcname_map.items():
            if isinstance(file_or_content, (str, Path)):
                zip_file.write(file_or_content, arcname)
            elif isinstance(file_or_content, bytes):
                zip_file.writestr(str(arcname), file_or_content)
            else:
                raise TypeError("创建zip的映射字典的键需要是str | Path | bytes")
