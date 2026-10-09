if __name__ == '__main__':
    import argparse
    import json
    import subprocess
    from pathlib import Path
    from migrator.core import Ledger, album_date, find_exiftool, scan
    from migrator.engine import Album, Control, run
    parser = argparse.ArgumentParser(description='CCD LINE Album Migrator')
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--check-output', type=Path)
    parser.add_argument('--dry-run', type=Path)
    parser.add_argument('--date')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--exiftool', default='')
    args = parser.parse_args()
    if args.self_check:
        tool = find_exiftool(args.exiftool)
        version = subprocess.run([tool, '-ver'], capture_output=True, check=True, timeout=15).stdout.decode().strip()
        result = json.dumps({'exiftool': version, 'date_parser': album_date('9-5-68').isoformat()})
        if args.check_output:
            args.check_output.write_text(result, encoding='utf-8')
        else:
            print(result)
    elif args.dry_run:
        if not args.date or not args.output:
            parser.error('--dry-run requires --date and --output outside the source folder')
        source = args.dry_run.resolve()
        output = args.output.resolve()
        if output == source or source in output.parents:
            parser.error('--output must be outside the source folder')
        photos = scan(source)
        if not photos or any(p.error for p in photos):
            parser.error('no supported photos, or corrupt files detected')
        ledger = Ledger(output / 'state.sqlite3')
        try:
            run([Album(source, album_date(args.date), photos)], ledger, output / 'copies',
                find_exiftool(args.exiftool), Control(), lambda text, done, total: print(f'{done}/{total} {text}'))
            ledger.export(output / 'report.csv')
        finally:
            ledger.close()
    else:
        from migrator.gui import main
        main()
