#!/usr/bin/env python3
"""Corrige les SIRET d'un CSV en les paddant à 14 chiffres avec des zéros à gauche."""
import csv
import sys
import os

def fix_siret(input_path, siret_column=1):
    """
    Pad les SIRET à 14 chiffres (zéros à gauche).
    siret_column: index de la colonne SIRET (0-based), défaut=1 (colonne B)
    """
    # Détecte le délimiteur
    with open(input_path, 'r', encoding='utf-8-sig') as f:
        sample = f.read(4096)
    delimiter = ';' if sample.count(';') > sample.count(',') else ','

    # Lit le CSV
    with open(input_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f, delimiter=delimiter)
        rows = list(reader)

    # Corrige les SIRET (skip header)
    fixed = 0
    for i, row in enumerate(rows):
        if i == 0:
            continue
        if len(row) > siret_column:
            val = row[siret_column].strip()
            if val.isdigit() and len(val) < 14:
                row[siret_column] = val.zfill(14)
                fixed += 1

    # Écrit le résultat
    output_path = input_path.replace('.csv', '_fixed.csv')
    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerows(rows)

    print(f"Corrigé {fixed} SIRET dans {output_path}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <fichier.csv> [colonne_siret (défaut: 1)]")
        sys.exit(1)
    col = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    fix_siret(sys.argv[1], col)
