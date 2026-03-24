"""
Connexion MongoDB et références aux collections.
"""

import os
import sys
import logging
from functools import wraps
from flask import jsonify
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from common.config import DEBUG

logger = logging.getLogger(__name__)

# =============================================================================
# Validation URI
# =============================================================================

MONGO_URI_ENV = os.environ.get('MONGO_URI', '').strip()


def validate_mongo_uri(uri):
    """Vérifie si l'URI MongoDB semble valide"""
    if not uri:
        return False
    if not uri.startswith('mongodb://') and not uri.startswith('mongodb+srv://'):
        return False
    if '//' in uri.split('://')[1].split('?')[0] or '..' in uri or '@.' in uri or './' in uri:
        return False
    try:
        after_protocol = uri.split('://')[1]
        host_part = after_protocol.split('@')[1].split('/')[0] if '@' in after_protocol else after_protocol.split('/')[0]
        if not host_part or host_part.startswith('.') or host_part.endswith('.'):
            return False
    except (IndexError, ValueError):
        return False
    return True


if not validate_mongo_uri(MONGO_URI_ENV):
    sys.stderr.write("ERREUR: MONGO_URI invalide. Doit commencer par mongodb:// ou mongodb+srv://\n")
    sys.exit(1)

MONGO_URI = MONGO_URI_ENV

# =============================================================================
# Connexion
# =============================================================================

MONGO_CONNECTION_ERROR = None


def resolve_srv_to_standard(srv_uri):
    """Résout une URI SRV MongoDB en format standard"""
    try:
        import dns.resolver
        from urllib.parse import urlparse

        parsed = urlparse(srv_uri.replace('mongodb+srv://', 'https://'))
        username = parsed.username
        password = parsed.password
        host = parsed.hostname

        logger.info(f"Résolution SRV pour: {host}")

        srv_records = dns.resolver.resolve(f'_mongodb._tcp.{host}', 'SRV')
        hosts = []
        for srv in srv_records:
            target = str(srv.target).rstrip('.')
            port = srv.port
            hosts.append(f"{target}:{port}")

        logger.info(f"Hosts trouvés: {hosts}")

        hosts_str = ','.join(hosts)
        standard_uri = f"mongodb://{username}:{password}@{hosts_str}/admin?authSource=admin&ssl=true&replicaSet=atlas-{host.split('.')[0].split('-')[-1]}-shard-0"

        return standard_uri
    except Exception as e:
        logger.error(f"Erreur résolution SRV: {type(e).__name__}: {e}")
        return None


def connect_mongodb(uri, use_srv=True):
    """Tente de se connecter à MongoDB avec fallback sur format standard"""
    global MONGO_CONNECTION_ERROR
    try:
        logger.info(f"Connexion MongoDB avec format {'SRV' if use_srv else 'standard'}...")
        logger.info(f"URI hosts: {uri.split('@')[1].split('/')[0] if '@' in uri else 'unknown'}")
        is_local = 'localhost' in uri or '127.0.0.1' in uri
        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=15000,
            connectTimeoutMS=15000,
            socketTimeoutMS=30000,
            retryWrites=True,
            w='majority',
            tls=not is_local
        )
        client.admin.command('ping')
        logger.info("Connexion MongoDB établie avec succès!")
        MONGO_CONNECTION_ERROR = None
        return client
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(f"Erreur connexion MongoDB: {error_msg}")
        MONGO_CONNECTION_ERROR = error_msg

        if use_srv and '+srv' in uri:
            logger.info("Tentative avec format standard (résolution manuelle SRV)...")
            standard_uri = resolve_srv_to_standard(uri)
            if standard_uri:
                return connect_mongodb(standard_uri, use_srv=False)

        return None


logger.info("Tentative de connexion MongoDB...")
logger.info(f"URI format: {'SRV' if '+srv' in MONGO_URI else 'standard'}")

mongo_client = connect_mongodb(MONGO_URI)

db = mongo_client['invoice_generator'] if mongo_client is not None else None
users_collection = db['users'] if db is not None else None
email_config_collection = db['email_config'] if db is not None else None
invoice_history_collection = db['invoice_history'] if db is not None else None
clients_collection = db['clients'] if db is not None else None
counters_collection = db['counters'] if db is not None else None

# =============================================================================
# Helpers liés à la DB
# =============================================================================


def require_db(f):
    """Décorateur pour vérifier la connexion à la base de données"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if mongo_client is None or db is None:
            logger.error("Base de données non disponible")
            return jsonify({'error': 'Service temporairement indisponible'}), 503
        return f(*args, **kwargs)
    return decorated_function


def reserve_invoice_numbers(prefix, count):
    """Réserve un bloc de numéros de facture de façon atomique."""
    result = counters_collection.find_one_and_update(
        {'_id': f'invoice_seq_{prefix}'},
        {'$inc': {'seq': count}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return result['seq'] - count + 1


def init_invoice_counter(prefix):
    """Initialise le compteur pour un préfixe donné en se basant sur l'historique existant."""
    max_seq = 0
    for inv in invoice_history_collection.find({}, {'invoice_number': 1}):
        num = inv.get('invoice_number', '')
        if num.startswith(prefix):
            parts = num.rsplit('-', 1)
            if len(parts) == 2:
                try:
                    seq = int(parts[1])
                    if seq > max_seq:
                        max_seq = seq
                except ValueError:
                    pass

    result = counters_collection.find_one_and_update(
        {'_id': f'invoice_seq_{prefix}', 'seq': {'$lt': max_seq}},
        {'$set': {'seq': max_seq}},
        upsert=False,
        return_document=True
    )
    if not result:
        existing = counters_collection.find_one({'_id': f'invoice_seq_{prefix}'})
        if existing:
            return existing['seq']
        try:
            counters_collection.insert_one({'_id': f'invoice_seq_{prefix}', 'seq': max_seq})
            logger.info(f"Compteur initialisé pour {prefix}: seq={max_seq}")
        except Exception:
            existing = counters_collection.find_one({'_id': f'invoice_seq_{prefix}'})
            if existing:
                return existing['seq']
    return max_seq
