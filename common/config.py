"""
Configuration et constantes de l'application.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Environment
# =============================================================================

ENV = os.environ.get('FLASK_ENV', 'production')
DEBUG = ENV == 'development'
VERSION = '1.0.0'

# =============================================================================
# Validation des variables d'environnement requises
# =============================================================================

REQUIRED_ENV_VARS = {
    'MONGO_URI': 'URI de connexion MongoDB (mongodb:// ou mongodb+srv://)',
    'ADMIN_PASSWORD': 'Mot de passe du super admin',
}

_missing_vars = [
    f"  - {var}: {desc}"
    for var, desc in REQUIRED_ENV_VARS.items()
    if not os.environ.get(var, '').strip()
]

if _missing_vars:
    sys.stderr.write("\n" + "=" * 60 + "\n")
    sys.stderr.write("ERREUR: Variables d'environnement manquantes !\n")
    sys.stderr.write("=" * 60 + "\n")
    sys.stderr.write("\n".join(_missing_vars) + "\n")
    sys.stderr.write("\nVérifiez votre fichier .env ou vos variables d'environnement.\n")
    sys.stderr.write("=" * 60 + "\n\n")
    sys.exit(1)

# =============================================================================
# Chemins et constantes
# =============================================================================

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

ALLOWED_EXTENSIONS = {'csv'}
EMAIL_CONFIG_FILE = os.path.join(BASE_DIR, 'email_config.json')
INVOICE_HISTORY_FILE = os.path.join(BASE_DIR, 'invoice_history.json')
BATCH_DATA_FILE = 'batch_data.json'
LOGO_PATH = os.path.join(BASE_DIR, 'logo.png')
LOGO_EMAIL_PATH = os.path.join(BASE_DIR, 'logo_email.png')

# =============================================================================
# Rate Limiting
# =============================================================================

LOGIN_LIMIT = "5 per minute"
EMAIL_LIMIT = "10 per minute"
API_LIMIT = "60 per minute"
