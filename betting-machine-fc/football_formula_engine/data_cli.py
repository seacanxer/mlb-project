"""Read-only Football-Data manifest builder. It never publishes or modifies source data."""
import argparse
import json

from .data import dataset_manifest, load_football_data_csv


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv')
    parser.add_argument('--competition', required=True)
    parser.add_argument('--season', required=True)
    parser.add_argument('--timezone', required=True, help='IANA zone with tzdata, UTC, or verified fixed offset')
    args = parser.parse_args(argv)
    matches, quotes = load_football_data_csv(
        args.csv, competition_id=args.competition, season=args.season, timezone_name=args.timezone)
    print(json.dumps(dataset_manifest(matches, quotes), sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
