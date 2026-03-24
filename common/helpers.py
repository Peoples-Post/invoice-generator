"""
Fonctions utilitaires partagées.
"""

import os
import re
import time
import logging

from common.config import ALLOWED_EXTENSIONS

logger = logging.getLogger(__name__)

# =============================================================================
# Validation
# =============================================================================


def validate_email(email):
    """Valide le format d'une adresse email"""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password):
    """Valide la force d'un mot de passe (min 6 caractères)"""
    return password and len(password) >= 6


def sanitize_string(value, max_length=500):
    """Nettoie et limite la longueur d'une chaîne"""
    if not isinstance(value, str):
        return ''
    return value.strip()[:max_length]


def allowed_file(filename):
    """Vérifie si l'extension du fichier est autorisée"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# =============================================================================
# Sécurité fichiers
# =============================================================================


def safe_filepath(base_dir, *parts):
    """Construit un chemin fichier sécurisé et vérifie qu'il reste dans base_dir.

    Protège contre les attaques path traversal (ex: ../../etc/passwd).
    Retourne le chemin résolu ou None si le chemin sort du répertoire autorisé.
    """
    filepath = os.path.realpath(os.path.join(base_dir, *parts))
    base_real = os.path.realpath(base_dir)
    if not filepath.startswith(base_real + os.sep) and filepath != base_real:
        return None
    return filepath


# =============================================================================
# CSV
# =============================================================================

# Cache CSV parsé en mémoire
_csv_cache = {}
_CSV_CACHE_TTL = 600  # 10 minutes


def get_parsed_csv(filepath):
    """Retourne le CSV parsé depuis le cache ou le parse et le met en cache"""
    from invoice_generator import parse_csv

    now = time.time()
    if filepath in _csv_cache:
        data, ts = _csv_cache[filepath]
        if now - ts < _CSV_CACHE_TTL:
            return data
    data = parse_csv(filepath)
    _csv_cache[filepath] = (data, now)
    # Nettoyage des entrées expirées
    expired = [k for k, (_, ts) in _csv_cache.items() if now - ts >= _CSV_CACHE_TTL]
    for k in expired:
        del _csv_cache[k]
    return data


# =============================================================================
# Helpers factures
# =============================================================================


def calculate_total_ht(rows):
    """Calcule le total HT à partir des lignes CSV"""
    return sum(
        float(row.get('Prix', '0').replace(',', '.') or '0') *
        int(float(row.get('Quantité', '1').replace(',', '.') or '1'))
        for row in rows
    )


def clean_siret(siret):
    """Nettoie un SIRET en ne gardant que les chiffres"""
    if not siret:
        return ''
    return ''.join(c for c in str(siret) if c.isdigit())


def extract_period(rows):
    """Extrait la période de facturation depuis les lignes CSV"""
    if not rows:
        return ''
    start_date = rows[0].get('Invoice Staring date', '')
    end_date = rows[0].get('Invoice Ending date', '')
    return f"du {start_date} au {end_date}" if start_date and end_date else ''
