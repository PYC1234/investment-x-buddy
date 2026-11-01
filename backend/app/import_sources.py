"""Usage: python -m app.import_sources path/to/public-source-bundle.json"""
import argparse
from pathlib import Path
from app.core.config import get_settings
from app.services.research_sources import SourceBundle, load_bundle


def main():
    parser = argparse.ArgumentParser(description='校验并导入公开研究资料；不会自动下载或调用模型')
    parser.add_argument('file', type=Path)
    args = parser.parse_args()
    raw = args.file.read_bytes()
    if len(raw) > 3 * 1024 * 1024:
        parser.error('资料包不能超过 3 MB')
    bundle = SourceBundle.model_validate_json(raw)
    folder = get_settings().research_data_dir
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'{bundle.symbol}.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(bundle.model_dump_json(indent=2), encoding='utf-8')
    temp.replace(target)
    _, revision = load_bundle(folder, bundle.symbol)
    print(f'Imported {bundle.symbol}; revision={revision}')


if __name__ == '__main__':
    main()
