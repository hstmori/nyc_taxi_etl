"""Download official monthly source files; explicit --overwrite required to replace files."""
import argparse
from pathlib import Path
from urllib.request import urlopen
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--month', action='append', required=True, help='YYYY-MM; repeat for several months')
    parser.add_argument('--destination', type=Path, default=Path('data/raw'))
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    from datetime import datetime
    for month in args.month:
        if datetime.strptime(month, '%Y-%m').strftime('%Y-%m') != month:
            raise ValueError('Month must use YYYY-MM')
    args.destination.mkdir(parents=True, exist_ok=True)
    files = [(f'yellow_tripdata_{m}.parquet', f'https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{m}.parquet') for m in args.month]
    files.append(('taxi_zone_lookup.csv', 'https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv'))
    for filename, url in files:
        destination = args.destination / filename
        if destination.exists() and not args.overwrite:
            print('SKIP', destination)
            continue
        temporary = destination.with_suffix(destination.suffix + '.part')
        try:
            with urlopen(url, timeout=120) as response, temporary.open('wb') as output:
                shutil.copyfileobj(response, output)
            if filename.endswith('.parquet'):
                with temporary.open('rb') as stream:
                    if stream.read(4) != b'PAR1':
                        raise ValueError('Response is not a Parquet file')
            temporary.replace(destination)
            print('DOWNLOADED', destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


if __name__ == '__main__':
    main()
