"""
Blueprint System : health check, status, debug files.
"""

import os
import shutil
import zipfile
import logging
from io import BytesIO
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

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


@system_bp.route('/api/debug/files/download', methods=['POST'])
@login_required
def debug_download_files():
    """Télécharge les fichiers/dossiers sélectionnés dans un ZIP"""
    if not current_user.is_admin():
        return jsonify({'error': 'Accès refusé'}), 403

    data = request.json
    items = data.get('items', [])

    if not items:
        return jsonify({'error': 'Aucun élément sélectionné'}), 400

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for item in items:
            folder_name = item.get('folder')
            rel_path = item.get('path')

            if folder_name == 'output':
                base_dir = current_app.config['OUTPUT_FOLDER']
            elif folder_name == 'uploads':
                base_dir = current_app.config['UPLOAD_FOLDER']
            else:
                continue

            filepath = safe_filepath(base_dir, rel_path)
            if not filepath:
                continue

            if os.path.isfile(filepath):
                # Fichier seul : conserver la structure dossier/fichier
                arcname = os.path.join(folder_name, rel_path)
                zf.write(filepath, arcname)
            elif os.path.isdir(filepath):
                # Dossier entier : parcourir récursivement
                for root, dirs, files in os.walk(filepath):
                    for f in files:
                        abs_path = os.path.join(root, f)
                        arc_rel = os.path.relpath(abs_path, base_dir)
                        arcname = os.path.join(folder_name, arc_rel)
                        zf.write(abs_path, arcname)

    zip_buffer.seek(0)
    zip_name = f"debug_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=zip_name
    )


@system_bp.route('/api/debug/files/upload', methods=['POST'])
@login_required
def debug_upload_files():
    """Importe un ZIP et restaure les fichiers dans output/ et uploads/"""
    if not current_user.is_admin():
        return jsonify({'error': 'Accès refusé'}), 403

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'Aucun fichier fourni'}), 400

    if not file.filename.lower().endswith('.zip'):
        return jsonify({'error': 'Le fichier doit être un ZIP'}), 400

    # Sauvegarder sur disque (Python 3.9 ne supporte pas ZipFile sur SpooledTemporaryFile)
    import tempfile
    tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    try:
        file.save(tmp_zip.name)
        zf = zipfile.ZipFile(tmp_zip.name, 'r')
    except zipfile.BadZipFile:
        os.unlink(tmp_zip.name)
        return jsonify({'error': 'Fichier ZIP invalide'}), 400

    restored = 0
    errors = []

    folder_map = {
        'output': current_app.config['OUTPUT_FOLDER'],
        'uploads': current_app.config['UPLOAD_FOLDER']
    }

    for member in zf.namelist():
        # Ignorer les dossiers vides et fichiers cachés
        if member.endswith('/') or '/__MACOSX' in member or member.startswith('__MACOSX'):
            continue

        # Le premier segment du chemin doit être output/ ou uploads/
        parts = member.split('/', 1)
        if len(parts) < 2:
            continue

        folder_name = parts[0]
        rel_path = parts[1]

        if folder_name not in folder_map:
            errors.append(f"Dossier racine ignoré: {folder_name}")
            continue

        base_dir = folder_map[folder_name]
        target_path = safe_filepath(base_dir, rel_path)
        if not target_path:
            errors.append(f"Chemin invalide: {member}")
            continue

        # Créer les dossiers parents
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        # Extraire le fichier
        with zf.open(member) as src, open(target_path, 'wb') as dst:
            dst.write(src.read())
        restored += 1

    zf.close()
    os.unlink(tmp_zip.name)

    logger.info(f"Import ZIP: {restored} fichiers restaurés par {current_user.email}")

    return jsonify({
        'success': True,
        'restored': restored,
        'errors': errors,
        'message': f'{restored} fichier(s) restauré(s)'
    })
