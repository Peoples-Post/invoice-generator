"""
Service d'envoi d'emails via l'API Brevo.
Inclut : config email, envoi factures/relances/bienvenue, templates HTML.
"""

import os
import json
import base64
import secrets
import logging
import urllib.request
import urllib.error

from common.config import DEBUG, EMAIL_CONFIG_FILE, LOGO_EMAIL_PATH
from common.database import email_config_collection

logger = logging.getLogger(__name__)

# =============================================================================
# Config email
# =============================================================================


def load_email_config():
    """Charge la configuration email depuis MongoDB"""
    config = email_config_collection.find_one({'_id': 'main'})
    if config:
        config.pop('_id', None)
    elif os.path.exists(EMAIL_CONFIG_FILE):
        with open(EMAIL_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            save_email_config(config)
    else:
        config = {}

    brevo_key = os.environ.get('BREVO_API_KEY', '').strip()
    if brevo_key:
        config['smtp_password'] = brevo_key

    return config


def save_email_config(config):
    """Sauvegarde la configuration email dans MongoDB"""
    config_copy = dict(config)
    config_copy['_id'] = 'main'
    email_config_collection.replace_one({'_id': 'main'}, config_copy, upsert=True)


# =============================================================================
# Utilitaires
# =============================================================================


def generate_temp_password(length=12):
    """Génère un mot de passe temporaire aléatoire (cryptographiquement sûr)"""
    import string
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def format_email_body(template, invoice_data):
    """Formate le corps de l'email avec les données de la facture"""
    return template.format(
        client_name=invoice_data.get('client_name', ''),
        company_name=invoice_data.get('company_name', ''),
        invoice_number=invoice_data.get('invoice_number', ''),
        total_ttc=invoice_data.get('total_ttc_formatted', ''),
        total_ht=invoice_data.get('total_ht_formatted', ''),
        period=invoice_data.get('period', ''),
        reminder_count=invoice_data.get('reminder_count', 1)
    )


# =============================================================================
# Envoi générique via API Brevo
# =============================================================================


def send_email_via_api(to_email, to_name, subject, html_content, text_content=None, attachment=None, attachment_name=None):
    """Envoie un email via l'API HTTP de Brevo"""
    email_config = load_email_config()

    api_key = email_config.get('smtp_password', '')
    if not api_key:
        return {'success': False, 'error': 'Clé API Brevo non configurée'}

    sender_email = email_config.get('sender_email') or email_config.get('smtp_username', '')
    sender_name = email_config.get('sender_name', 'Peoples Post')

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email, "name": to_name or to_email}],
        "subject": subject,
        "htmlContent": html_content
    }

    if text_content:
        payload["textContent"] = text_content

    if attachment and attachment_name:
        payload["attachment"] = [{
            "name": attachment_name,
            "content": base64.b64encode(attachment).decode('utf-8')
        }]

    try:
        req = urllib.request.Request(
            'https://api.brevo.com/v3/smtp/email',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'accept': 'application/json',
                'api-key': api_key,
                'content-type': 'application/json'
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            logger.info(f"Email envoyé via API Brevo à {to_email}: {result}")
            return {'success': True, 'message_id': result.get('messageId')}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        logger.error(f"Erreur API Brevo: {e.code} - {error_body}")
        return {'success': False, 'error': f'Erreur API Brevo: {error_body}'}
    except urllib.error.URLError as e:
        logger.error(f"Erreur connexion API Brevo: {e}")
        return {'success': False, 'error': f'Erreur connexion: {str(e)}'}
    except Exception as e:
        logger.error(f"Erreur envoi email API: {e}")
        return {'success': False, 'error': str(e)}


# =============================================================================
# Templates HTML email
# =============================================================================


def create_html_email(body_text, invoice_data, email_type='invoice'):
    """Crée un email HTML stylisé avec le branding Peoples Post"""
    header_colors = {
        'invoice': '#3026f0',
        'reminder_1': '#f59e0b',
        'reminder_2': '#f97316',
        'reminder_3': '#ef4444',
        'reminder_4': '#7f1d1d'
    }

    header_titles = {
        'invoice': 'Votre Facture',
        'reminder_1': 'Rappel de Paiement',
        'reminder_2': 'Action Requise',
        'reminder_3': 'Dernier Avis',
        'reminder_4': 'Suspension de Compte'
    }

    header_color = header_colors.get(email_type, '#3026f0')
    header_title = header_titles.get(email_type, 'Votre Facture')

    body_html = body_text.replace('\n', '<br>')

    badge_html = ''
    if email_type == 'reminder_2':
        badge_html = '<span style="display: inline-block; background-color: #fff3cd; color: #856404; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-bottom: 15px;">URGENT</span><br>'
    elif email_type == 'reminder_3':
        badge_html = '<span style="display: inline-block; background-color: #f8d7da; color: #721c24; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-bottom: 15px;">SUSPENSION IMMINENTE</span><br>'
    elif email_type == 'reminder_4':
        badge_html = '<span style="display: inline-block; background-color: #7f1d1d; color: #ffffff; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-bottom: 15px;">COMPTE SUSPENDU</span><br>'

    html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f0f2f5;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f0f2f5;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="margin: 0 auto;">
                    <tr>
                        <td style="background: linear-gradient(135deg, {header_color} 0%, {'#1a1aad' if email_type == 'invoice' else header_color} 100%); padding: 30px 40px; text-align: center; border-radius: 16px 16px 0 0;">
                            <img src="https://pp-invoces-generator.up.railway.app/static/logo.png" alt="Peoples Post" style="height: 90px; margin: 0 auto 12px auto; display: block;">
                            <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 700; letter-spacing: -0.5px;">{header_title}</h1>
                        </td>
                    </tr>
                    <tr>
                        <td style="background-color: #ffffff; padding: 0; border-radius: 0 0 16px 16px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="padding: 30px 40px; border-bottom: 1px solid #eef0f2;">
                                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                            <tr>
                                                <td style="text-align: left; vertical-align: middle;">
                                                    <span style="color: #8b8e94; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;">Facture</span><br>
                                                    <span style="color: #1a1a2e; font-size: 20px; font-weight: 700;">{invoice_data.get('invoice_number', '')}</span>
                                                </td>
                                                <td style="text-align: right; vertical-align: middle;">
                                                    <span style="color: #8b8e94; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;">Total TTC</span><br>
                                                    <span style="color: {header_color}; font-size: 32px; font-weight: 800;">{invoice_data.get('total_ttc_formatted', '')}</span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="padding: 40px;">
                                        {badge_html}
                                        <div style="color: #4a4a5a; font-size: 15px; line-height: 1.8;">
                                            {body_html}
                                        </div>
                                    </td>
                                </tr>
                            </table>
                            {'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td style="padding: 0 40px 40px; text-align: center;"><a href="mailto:victor.estines@peoplespost.fr?subject=Paiement facture ' + invoice_data.get('invoice_number', '') + '" style="display: inline-block; background-color: ' + header_color + '; color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 50px; font-weight: 600; font-size: 15px; box-shadow: 0 4px 15px ' + header_color + '40;">Nous contacter</a></td></tr></table>' if email_type != 'invoice' else ''}
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="background-color: #f8f9fb; padding: 30px 40px; border-radius: 0 0 16px 16px; border-top: 1px solid #eef0f2;">
                                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                            <tr>
                                                <td style="text-align: center;">
                                                    <p style="color: #1a1a2e; font-size: 14px; font-weight: 700; margin: 0 0 8px 0;">Peoples Post SAS</p>
                                                    <p style="color: #8b8e94; font-size: 13px; margin: 0; line-height: 1.7;">
                                                        22 rue Emeriau, 75015 Paris<br>
                                                        <a href="mailto:victor.estines@peoplespost.fr" style="color: {header_color}; text-decoration: none;">victor.estines@peoplespost.fr</a><br>
                                                        SIRET 98004432500010
                                                    </p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 25px 20px; text-align: center;">
                            <p style="color: #a0a3a8; font-size: 11px; margin: 0; line-height: 1.6;">
                                Ce message et ses pièces jointes sont confidentiels et destinés exclusivement au destinataire.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

    return html


def create_html_email_preview(body_text, invoice_data, email_type='invoice'):
    """Crée un email HTML pour prévisualisation (avec logo en base64)"""
    header_colors = {
        'invoice': '#3026f0',
        'reminder_1': '#f59e0b',
        'reminder_2': '#f97316',
        'reminder_3': '#ef4444',
        'reminder_4': '#7f1d1d'
    }

    header_titles = {
        'invoice': 'Votre Facture',
        'reminder_1': 'Rappel de Paiement',
        'reminder_2': 'Action Requise',
        'reminder_3': 'Dernier Avis',
        'reminder_4': 'Suspension de Compte'
    }

    header_color = header_colors.get(email_type, '#3026f0')
    header_title = header_titles.get(email_type, 'Votre Facture')

    logo_src = '/static/logo_email.png'
    if os.path.exists(LOGO_EMAIL_PATH):
        with open(LOGO_EMAIL_PATH, 'rb') as f:
            logo_base64 = base64.b64encode(f.read()).decode('utf-8')
            logo_src = f'data:image/png;base64,{logo_base64}'

    body_html = body_text.replace('\n', '<br>')

    badge_html = ''
    if email_type == 'reminder_2':
        badge_html = '<span style="display: inline-block; background-color: #fff3cd; color: #856404; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-bottom: 15px;">URGENT</span><br>'
    elif email_type == 'reminder_3':
        badge_html = '<span style="display: inline-block; background-color: #f8d7da; color: #721c24; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-bottom: 15px;">SUSPENSION IMMINENTE</span><br>'
    elif email_type == 'reminder_4':
        badge_html = '<span style="display: inline-block; background-color: #7f1d1d; color: #ffffff; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-bottom: 15px;">COMPTE SUSPENDU</span><br>'

    html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Prévisualisation Email - {header_title}</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f0f2f5;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f0f2f5;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="margin: 0 auto;">
                    <tr>
                        <td style="background: linear-gradient(135deg, {header_color} 0%, {'#1a1aad' if email_type == 'invoice' else header_color} 100%); padding: 30px 40px; text-align: center; border-radius: 16px 16px 0 0;">
                            <img src="{logo_src}" alt="Peoples Post" style="height: 90px; margin: 0 auto 12px auto; display: block;">
                            <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 700; letter-spacing: -0.5px;">{header_title}</h1>
                        </td>
                    </tr>
                    <tr>
                        <td style="background-color: #ffffff; padding: 0; border-radius: 0 0 16px 16px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="padding: 30px 40px; border-bottom: 1px solid #eef0f2;">
                                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                            <tr>
                                                <td style="text-align: left; vertical-align: middle;">
                                                    <span style="color: #8b8e94; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;">Facture</span><br>
                                                    <span style="color: #1a1a2e; font-size: 20px; font-weight: 700;">{invoice_data.get('invoice_number', '')}</span>
                                                </td>
                                                <td style="text-align: right; vertical-align: middle;">
                                                    <span style="color: #8b8e94; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;">Total TTC</span><br>
                                                    <span style="color: {header_color}; font-size: 32px; font-weight: 800;">{invoice_data.get('total_ttc_formatted', '')}</span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="padding: 40px;">
                                        {badge_html}
                                        <div style="color: #4a4a5a; font-size: 15px; line-height: 1.8;">
                                            {body_html}
                                        </div>
                                    </td>
                                </tr>
                            </table>
                            {'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td style="padding: 0 40px 40px; text-align: center;"><a href="#" style="display: inline-block; background-color: ' + header_color + '; color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 50px; font-weight: 600; font-size: 15px; box-shadow: 0 4px 15px ' + header_color + '40;">Nous contacter</a></td></tr></table>' if email_type != 'invoice' else ''}
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="background-color: #f8f9fb; padding: 30px 40px; border-radius: 0 0 16px 16px; border-top: 1px solid #eef0f2;">
                                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                            <tr>
                                                <td style="text-align: center;">
                                                    <p style="color: #1a1a2e; font-size: 14px; font-weight: 700; margin: 0 0 8px 0;">Peoples Post SAS</p>
                                                    <p style="color: #8b8e94; font-size: 13px; margin: 0; line-height: 1.7;">
                                                        22 rue Emeriau, 75015 Paris<br>
                                                        <a href="mailto:victor.estines@peoplespost.fr" style="color: {header_color}; text-decoration: none;">victor.estines@peoplespost.fr</a><br>
                                                        SIRET 98004432500010
                                                    </p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 25px 20px; text-align: center;">
                            <p style="color: #a0a3a8; font-size: 11px; margin: 0; line-height: 1.6;">
                                Ce message et ses pièces jointes sont confidentiels et destinés exclusivement au destinataire.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

    return html


# =============================================================================
# Emails de bienvenue
# =============================================================================


def create_welcome_email_html(user_name, user_email, temp_password):
    """Crée un email HTML de bienvenue pour les nouveaux utilisateurs"""

    html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f0f2f5;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f0f2f5;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="margin: 0 auto;">
                    <tr>
                        <td style="background: linear-gradient(135deg, #3026f0 0%, #1a1aad 100%); padding: 30px 40px; text-align: center; border-radius: 16px 16px 0 0;">
                            <img src="https://pp-invoces-generator.up.railway.app/static/logo.png" alt="Peoples Post" style="height: 90px; margin: 0 auto 12px auto; display: block;">
                            <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 700; letter-spacing: -0.5px;">Bienvenue !</h1>
                        </td>
                    </tr>
                    <tr>
                        <td style="background-color: #ffffff; padding: 0; border-radius: 0 0 16px 16px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="padding: 40px;">
                                        <p style="color: #1a1a2e; font-size: 18px; font-weight: 600; margin: 0 0 20px 0;">
                                            Bonjour {user_name or 'et bienvenue'} !
                                        </p>
                                        <p style="color: #4a4a5a; font-size: 15px; line-height: 1.8; margin: 0 0 25px 0;">
                                            Votre compte a été créé sur le <strong>Générateur de Factures Peoples Post</strong>.
                                            Vous pouvez maintenant vous connecter et commencer à générer vos factures.
                                        </p>
                                        <div style="background-color: #f8f9fb; border-radius: 12px; padding: 25px; margin: 25px 0; border-left: 4px solid #3026f0;">
                                            <p style="color: #1a1a2e; font-size: 14px; font-weight: 600; margin: 0 0 15px 0; text-transform: uppercase; letter-spacing: 0.5px;">
                                                Vos identifiants de connexion
                                            </p>
                                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                                <tr>
                                                    <td style="padding: 8px 0;">
                                                        <span style="color: #8b8e94; font-size: 13px;">Email :</span><br>
                                                        <span style="color: #1a1a2e; font-size: 16px; font-weight: 600;">{user_email}</span>
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding: 8px 0;">
                                                        <span style="color: #8b8e94; font-size: 13px;">Mot de passe temporaire :</span><br>
                                                        <span style="color: #3026f0; font-size: 16px; font-weight: 600; font-family: monospace; background-color: #eef0ff; padding: 4px 10px; border-radius: 4px;">{temp_password}</span>
                                                    </td>
                                                </tr>
                                            </table>
                                        </div>
                                        <p style="color: #ef4444; font-size: 14px; line-height: 1.6; margin: 0 0 25px 0; padding: 12px; background-color: #fef2f2; border-radius: 8px;">
                                            <strong>Important :</strong> Pour des raisons de sécurité, nous vous recommandons de changer votre mot de passe dès votre première connexion.
                                        </p>
                                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                            <tr>
                                                <td style="text-align: center; padding: 10px 0;">
                                                    <a href="https://pp-invoces-generator.up.railway.app/login" style="display: inline-block; background-color: #3026f0; color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 50px; font-weight: 600; font-size: 15px; box-shadow: 0 4px 15px rgba(48, 38, 240, 0.3);">
                                                        Se connecter
                                                    </a>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="background-color: #f8f9fb; padding: 30px 40px; border-radius: 0 0 16px 16px; border-top: 1px solid #eef0f2;">
                                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                            <tr>
                                                <td style="text-align: center;">
                                                    <p style="color: #1a1a2e; font-size: 14px; font-weight: 700; margin: 0 0 8px 0;">Peoples Post SAS</p>
                                                    <p style="color: #8b8e94; font-size: 13px; margin: 0; line-height: 1.7;">
                                                        22 rue Emeriau, 75015 Paris<br>
                                                        <a href="mailto:victor.estines@peoplespost.fr" style="color: #3026f0; text-decoration: none;">victor.estines@peoplespost.fr</a>
                                                    </p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 25px 20px; text-align: center;">
                            <p style="color: #a0a3a8; font-size: 11px; margin: 0; line-height: 1.6;">
                                Ce message et ses pièces jointes sont confidentiels et destinés exclusivement au destinataire.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

    return html


def send_welcome_email(user_email, user_name, temp_password):
    """Envoie un email de bienvenue au nouvel utilisateur via l'API Brevo"""

    text_content = f"""Bonjour {user_name or 'et bienvenue'} !

Votre compte a été créé sur le Générateur de Factures Peoples Post.

Vos identifiants de connexion :
- Email : {user_email}
- Mot de passe temporaire : {temp_password}

Important : Pour des raisons de sécurité, nous vous recommandons de changer votre mot de passe dès votre première connexion.

Connectez-vous sur : https://pp-invoces-generator.up.railway.app/login

Cordialement,
L'équipe Peoples Post
"""

    html_content = create_welcome_email_html(user_name, user_email, temp_password)

    return send_email_via_api(
        to_email=user_email,
        to_name=user_name or user_email,
        subject="Bienvenue sur le Générateur de Factures Peoples Post",
        html_content=html_content,
        text_content=text_content
    )


def send_client_welcome_email(client_email, client_name, temp_password):
    """Envoie un email de bienvenue au nouveau compte client via l'API Brevo"""

    text_content = f"""Bonjour {client_name} !

Votre espace client a été créé sur le portail Peoples Post.

Vos identifiants de connexion :
- Email : {client_email}
- Mot de passe temporaire : {temp_password}

Vous pouvez désormais accéder à votre espace client pour :
- Consulter vos factures
- Suivre votre historique de facturation
- Voir votre situation financière

Important : Pour des raisons de sécurité, nous vous recommandons de changer votre mot de passe dès votre première connexion.

Connectez-vous sur : https://pp-invoces-generator.up.railway.app/login

Cordialement,
L'équipe Peoples Post
"""

    html_content = f'''<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f0f2f5;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f0f2f5;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" width="600" cellspacing="0" cellpadding="0" align="center" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                    <tr>
                        <td style="background: linear-gradient(135deg, #3026f0 0%, #5046e5 100%); padding: 30px 40px; text-align: center;">
                            <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 600;">Bienvenue sur votre Espace Client</h1>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 40px;">
                            <p style="font-size: 16px; color: #333; line-height: 1.6; margin: 0 0 20px 0;">Bonjour <strong>{client_name}</strong>,</p>
                            <p style="font-size: 16px; color: #333; line-height: 1.6; margin: 0 0 20px 0;">Votre espace client a été créé sur le portail Peoples Post.</p>
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin: 25px 0;">
                                <tr>
                                    <td style="background-color: #f8f9fa; border-radius: 8px; padding: 20px; border-left: 4px solid #3026f0;">
                                        <p style="font-size: 14px; color: #666; margin: 0 0 10px 0; font-weight: 600;">Vos identifiants de connexion :</p>
                                        <p style="font-size: 14px; color: #333; margin: 0 0 5px 0;"><strong>Email :</strong> {client_email}</p>
                                        <p style="font-size: 14px; color: #333; margin: 0;"><strong>Mot de passe temporaire :</strong> <code style="background-color: #e9ecef; padding: 2px 8px; border-radius: 4px; font-family: monospace;">{temp_password}</code></p>
                                    </td>
                                </tr>
                            </table>
                            <p style="font-size: 16px; color: #333; line-height: 1.6; margin: 0 0 20px 0;">Vous pouvez désormais accéder à votre espace client pour :</p>
                            <ul style="font-size: 14px; color: #555; line-height: 1.8; padding-left: 20px; margin: 0 0 25px 0;">
                                <li>Consulter vos factures</li>
                                <li>Suivre votre historique de facturation</li>
                                <li>Voir votre situation financière</li>
                            </ul>
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td align="center" style="padding: 10px 0 25px 0;">
                                        <a href="https://pp-invoces-generator.up.railway.app/login" style="display: inline-block; background-color: #3026f0; color: #ffffff; text-decoration: none; padding: 14px 40px; border-radius: 8px; font-weight: 600; font-size: 16px;">Accéder à mon espace</a>
                                    </td>
                                </tr>
                            </table>
                            <p style="font-size: 14px; color: #888; line-height: 1.6; margin: 0; border-top: 1px solid #eee; padding-top: 20px;">
                                <strong>Important :</strong> Pour des raisons de sécurité, nous vous recommandons de changer votre mot de passe dès votre première connexion.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="background-color: #f8f9fa; padding: 25px 40px; text-align: center;">
                            <p style="font-size: 12px; color: #888; margin: 0;">Peoples Post - Votre partenaire logistique</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

    return send_email_via_api(
        to_email=client_email,
        to_name=client_name or client_email,
        subject="Bienvenue sur votre Espace Client Peoples Post",
        html_content=html_content,
        text_content=text_content
    )


# =============================================================================
# Envoi factures et relances
# =============================================================================


def send_invoice_email(invoice_data, email_config, batch_folder, include_detail=False):
    """Envoie un email HTML stylisé avec la facture en pièce jointe via l'API Brevo"""
    client_email = invoice_data.get('client_email', '')

    if not client_email:
        return {'success': False, 'error': 'Pas d\'adresse email pour ce client'}

    dev_recipient = os.environ.get('DEV_RECIPIENT_EMAIL', '')
    if DEBUG and dev_recipient:
        recipient_email = dev_recipient
        logger.info(f"[DEV] Redirection email vers {dev_recipient} (client réel: {client_email})")
    else:
        recipient_email = client_email

    api_key = email_config.get('smtp_password', '')
    if not api_key:
        return {'success': False, 'error': 'Clé API Brevo non configurée'}

    actual_sender_name = email_config.get('sender_name', 'Peoples Post')
    actual_sender_email = os.environ.get('SENDER_INVOICE_EMAIL') or email_config.get('sender_email', '')

    try:
        subject = email_config.get('email_subject', 'Votre facture Peoples Post').format(
            invoice_number=invoice_data.get('invoice_number', ''),
            client_name=invoice_data.get('client_name', ''),
            company_name=invoice_data.get('company_name', '')
        )

        body_text = format_email_body(
            email_config.get('email_template', ''),
            invoice_data
        )

        body_html = create_html_email(body_text, invoice_data, 'invoice')

        payload = {
            "sender": {"name": actual_sender_name, "email": actual_sender_email},
            "to": [{"email": recipient_email, "name": invoice_data.get('company_name', recipient_email)}],
            "cc": [{"email": "accounts@peoplespost.fr", "name": "Peoples Post Accounts" + (" debug" if DEBUG else "")}],
            "subject": subject,
            "htmlContent": body_html,
            "textContent": body_text
        }

        pdf_path = os.path.join(batch_folder, invoice_data.get('filename', ''))
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
                payload["attachment"] = [{
                    "name": invoice_data.get('filename', 'facture.pdf'),
                    "content": base64.b64encode(pdf_content).decode('utf-8')
                }]

        if include_detail:
            detail_filename = invoice_data.get('detail_filename', '')
            if detail_filename:
                detail_csv_path = os.path.join(batch_folder, detail_filename)
                if os.path.exists(detail_csv_path):
                    with open(detail_csv_path, 'rb') as f:
                        detail_content = f.read()
                    if "attachment" not in payload:
                        payload["attachment"] = []
                    payload["attachment"].append({
                        "name": detail_filename,
                        "content": base64.b64encode(detail_content).decode('utf-8')
                    })

        req = urllib.request.Request(
            'https://api.brevo.com/v3/smtp/email',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'accept': 'application/json',
                'api-key': api_key,
                'content-type': 'application/json'
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            logger.info(f"Email facture envoyé via API: {invoice_data.get('invoice_number')} -> {recipient_email}")
            return {'success': True, 'message_id': result.get('messageId')}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        logger.error(f"Erreur API Brevo facture {invoice_data.get('invoice_number')}: {e.code} - {error_body}")
        return {'success': False, 'error': f'Erreur API Brevo: {error_body}'}
    except urllib.error.URLError as e:
        logger.error(f"Erreur connexion API Brevo: {e}")
        return {'success': False, 'error': f'Erreur connexion: {str(e)}'}
    except Exception as e:
        logger.error(f"Erreur envoi facture {invoice_data.get('invoice_number')}: {e}")
        return {'success': False, 'error': f'Erreur: {str(e)}'}


def send_reminder_email(invoice_data, email_config, batch_folder, reminder_type=1):
    """Envoie un email HTML stylisé de relance avec la facture en pièce jointe via l'API Brevo"""
    client_email = invoice_data.get('client_email', '')

    if not client_email:
        return {'success': False, 'error': 'Pas d\'adresse email pour ce client'}

    dev_recipient = os.environ.get('DEV_RECIPIENT_EMAIL', '')
    if DEBUG and dev_recipient:
        recipient_email = dev_recipient
        logger.info(f"[DEV] Redirection relance vers {dev_recipient} (client réel: {client_email})")
    else:
        recipient_email = client_email

    api_key = email_config.get('smtp_password', '')
    if not api_key:
        return {'success': False, 'error': 'Clé API Brevo non configurée'}

    actual_sender_name = email_config.get('sender_name', 'Peoples Post')
    actual_sender_email = os.environ.get('SENDER_INVOICE_EMAIL') or email_config.get('sender_email', '')

    try:
        subject_key = f'reminder_{reminder_type}_subject'
        template_key = f'reminder_{reminder_type}_template'

        subject_template = email_config.get(subject_key, email_config.get('reminder_1_subject', 'RELANCE - Facture {invoice_number}'))
        subject = subject_template.format(
            invoice_number=invoice_data.get('invoice_number', ''),
            client_name=invoice_data.get('client_name', ''),
            company_name=invoice_data.get('company_name', '')
        )

        body_template = email_config.get(template_key, '')
        if not body_template:
            body_template = email_config.get('email_template', '')

        body_text = format_email_body(body_template, invoice_data)

        email_type = f'reminder_{reminder_type}'
        body_html = create_html_email(body_text, invoice_data, email_type)

        payload = {
            "sender": {"name": actual_sender_name, "email": actual_sender_email},
            "to": [{"email": recipient_email, "name": invoice_data.get('company_name', recipient_email)}],
            "cc": [{"email": "accounts@peoplespost.fr", "name": "Peoples Post Accounts" + (" debug" if DEBUG else "")}],
            "subject": subject,
            "htmlContent": body_html,
            "textContent": body_text
        }

        pdf_path = os.path.join(batch_folder, invoice_data.get('filename', ''))
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
                payload["attachment"] = [{
                    "name": invoice_data.get('filename', 'facture.pdf'),
                    "content": base64.b64encode(pdf_content).decode('utf-8')
                }]

        req = urllib.request.Request(
            'https://api.brevo.com/v3/smtp/email',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'accept': 'application/json',
                'api-key': api_key,
                'content-type': 'application/json'
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            logger.info(f"Relance R{reminder_type} envoyée via API: {invoice_data.get('invoice_number')} -> {recipient_email}")
            return {'success': True, 'message_id': result.get('messageId')}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        logger.error(f"Erreur API Brevo relance {invoice_data.get('invoice_number')}: {e.code} - {error_body}")
        return {'success': False, 'error': f'Erreur API Brevo: {error_body}'}
    except urllib.error.URLError as e:
        logger.error(f"Erreur connexion API Brevo: {e}")
        return {'success': False, 'error': f'Erreur connexion: {str(e)}'}
    except Exception as e:
        logger.error(f"Erreur relance {invoice_data.get('invoice_number')}: {e}")
        return {'success': False, 'error': f'Erreur: {str(e)}'}
