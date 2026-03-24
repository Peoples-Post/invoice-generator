"""
Blueprint System : health check, status, debug files.
"""

import os
import shutil
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user

from common.config import VERSION, ENV
from common.database import mongo_client, db, users_collection, invoice_history_collection, clients_collection, MONGO_CONNECTION_ERROR
from common.helpers import safe_filepath

logger = logging.getLogger(__name__)

system_bp = Blueprint('system', __name__)


# =============================================================================
# Health Check & Status
# =============================================================================

@system_bp.route('/health')
def health_check():
    """Endpoint de health check pour Railway et monitoring"""
    health = {
        'status': 'healthy',
        'version': VERSION,
        'environment': ENV,
        'timestamp': datetime.now().isoformat()
    }

    try:
        if mongo_client:
            mongo_client.admin.command('ping')
            health['database'] = 'connected'
        else:
            health['database'] = 'disconnected'
            health['status'] = 'degraded'
            if MONGO_CONNECTION_ERROR:
                health['startup_error'] = MONGO_CONNECTION_ERROR
    except Exception as e:
        health['database'] = 'error'
        health['database_error'] = str(e)
        health['status'] = 'unhealthy'

    status_code = 200 if health['status'] == 'healthy' else 503
    return jsonify(health), status_code


@system_bp.route('/api/status')
@login_required
def api_status():
    """Endpoint de status détaillé (authentifié)"""
    status = {
        'version': VERSION,
        'environment': ENV,
        'user': current_user.email,
        'timestamp': datetime.now().isoformat()
    }

    try:
        if db is not None:
            status['stats'] = {
                'users': users_collection.count_documents({}),
                'invoices': invoice_history_collection.count_documents({}),
                'clients': clients_collection.count_documents({})
            }
    except Exception as e:
        status['stats_error'] = str(e)

    return jsonify(status)


# =============================================================================
# Debug (admin uniquement)
# =============================================================================

@system_bp.route('/api/debug/files')
@login_required
def debug_files():
    """Liste les fichiers des répertoires output et uploads (admin uniquement)"""
    if not current_user.is_admin():
        return jsonify({'error': 'Accès refusé'}), 403

    result = {}
    for folder_name, folder_path in [
        ('output', current_app.config['OUTPUT_FOLDER']),
        ('uploads', current_app.config['UPLOAD_FOLDER'])
    ]:
        files = []
        total_size = 0
        if os.path.exists(folder_path):
            for root, dirs, filenames in os.walk(folder_path):
                for f in filenames:
                    filepath = os.path.join(root, f)
                    rel_path = os.path.relpath(filepath, folder_path)
                    size = os.path.getsize(filepath)
                    total_size += size
                    files.append({
                        'path': rel_path,
                        'size': size,
                        'modified': datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
                    })
        files.sort(key=lambda x: x['modified'], reverse=True)
        result[folder_name] = {
            'base_path': folder_path,
            'files': files,
            'total_size': total_size,
            'file_count': len(files)
        }
    return jsonify(result)


@system_bp.route('/api/debug/files', methods=['DELETE'])
@login_required
def debug_delete_files():
    """Supprime des fichiers ou dossiers sélectionnés (admin uniquement)"""
    if not current_user.is_admin():
        return jsonify({'error': 'Accès refusé'}), 403

    data = request.json
    items = data.get('items', [])

    deleted = 0
    errors = []

    for item in items:
        folder_name = item.get('folder')
        rel_path = item.get('path')

        if folder_name == 'output':
            base_dir = current_app.config['OUTPUT_FOLDER']
        elif folder_name == 'uploads':
            base_dir = current_app.config['UPLOAD_FOLDER']
        else:
            errors.append(f"Dossier inconnu: {folder_name}")
            continue

        filepath = safe_filepath(base_dir, rel_path)
        if not filepath:
            errors.append(f"Chemin invalide: {rel_path}")
            continue

        try:
            if os.path.isdir(filepath):
                shutil.rmtree(filepath)
                deleted += 1
            elif os.path.isfile(filepath):
                os.remove(filepath)
                deleted += 1
            else:
                errors.append(f"Introuvable: {rel_path}")
        except Exception as e:
            errors.append(f"Erreur {rel_path}: {str(e)}")

    return jsonify({
        'success': True,
        'deleted': deleted,
        'errors': errors
    })
