"""Minimal pairing client for testing the pairing API.

Usage: python tools/pair_client.py --server http://localhost:5000 --code <code>
"""
import argparse

import requests


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--server', default='http://localhost:5000')
    p.add_argument('--code')
    args = p.parse_args()
    if not args.code:
        print('Provide --code from the website pairing endpoint')
        return
    r = requests.post(args.server + '/api/pair/check', json={'code': args.code}, timeout=5)
    try:
        print(r.status_code, r.text)
    except Exception:
        print('Error', r)


if __name__ == '__main__':
    main()
