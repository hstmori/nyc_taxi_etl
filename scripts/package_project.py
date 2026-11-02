"""Build a small source/evidence ZIP, excluding local databases and source datasets."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parent.parent
    destination = root.parent / 'nyc-taxi-etl-source.zip'
    excluded = {'.git', '.venv', '__pycache__', '.pytest_cache', '.pbi', 'artifacts', 'data'}
    with ZipFile(destination, 'w', compression=ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob('*')):
            relative = path.relative_to(root)
            if path.is_file() and not any(p in excluded for p in relative.parts):
                archive.write(path, Path(root.name) / relative)
    print(destination)


if __name__ == '__main__':
    main()
