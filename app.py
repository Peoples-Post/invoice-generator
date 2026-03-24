#!/usr/bin/env python3
"""
Peoples Post - Application web de génération de factures
Point d'entrée de l'application.
"""

import os
from create_app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)
