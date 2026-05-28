#!/usr/bin/env python3
"""
Seed the address pool from a text file (one WEBD address per line).
Run once before starting the server.

Usage:
    python3 seed_addresses.py addresses.txt
"""
import sys
import db


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 seed_addresses.py <addresses.txt>")
        sys.exit(1)
    path = sys.argv[1]
    with open(path) as f:
        addresses = [line.strip() for line in f if line.strip().startswith('WEBD$')]
    if not addresses:
        print("No valid WEBD$ addresses found in file.")
        sys.exit(1)
    db.init_db()
    db.seed_address_pool(addresses)
    print(f"Seeded {len(addresses)} addresses into pool.")


if __name__ == '__main__':
    main()
