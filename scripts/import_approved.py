"""Copy selected, real approved SQLite records into PostgreSQL without replaying delivery.

DATABASE_URL must identify the target. Source records and all other local runs stay intact.
"""
import argparse
import json
from pathlib import Path

from signalbrief.config import Settings
from signalbrief.store import Store


def import_approved(source, target, run_ids):
    target.initialize()
    count = 0
    for run_id in run_ids:
        with source.transaction() as src, target.transaction() as dst:
            run = src.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if run is None or run['status'] != 'approved':
                raise ValueError('Import requires an existing approved run')
            existing = dst.execute('SELECT event_hash FROM runs WHERE id=?', (run_id,)).fetchone()
            if existing:
                if existing['event_hash'] != run['event_hash']:
                    raise ValueError('Target run conflicts with source')
                continue
            for table in ('runs', 'reports', 'audit', 'deliveries'):
                rows = [run] if table == 'runs' else src.execute(
                    f'SELECT * FROM {table} WHERE run_id=?', (run_id,)).fetchall()
                for row in rows:
                    values = dict(row)
                    if table == 'audit':
                        values.pop('id')
                    if table == 'deliveries' and values['status'] not in ('sent', 'cancelled'):
                        raise ValueError('Pending delivery cannot be imported')
                    columns = ','.join(values)
                    placeholders = ','.join('?' for _ in values)
                    dst.execute(f'INSERT INTO {table}({columns}) VALUES({placeholders})', tuple(values.values()))
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path('data/signalbrief.sqlite3'))
    parser.add_argument('--run-id', action='append', required=True)
    args = parser.parse_args()
    settings = Settings()
    url = settings.database_url.get_secret_value()
    if not url:
        raise SystemExit('Set DATABASE_URL for the PostgreSQL target')
    count = import_approved(Store(args.source), Store(settings.database_path, url), args.run_id)
    print(json.dumps({'imported_approved_runs': count, 'delivery_replayed': False}))


if __name__ == '__main__':
    main()
