IN PROGRESS...

INICIALIZAR O SERVIDOR FLASK:

flask --app app run
---

COMANDOS SQLITE:

rm -rf migrations               # Remove as migrações
rm database.db                  # Apaga o banco SQLite
flask db init                   # Inicia o banco
flask db migrate -m "Mensagem"  # Alterações no banco
flask db upgrade                # Recria o banco
---

# TODO: Mail Validation Settings
    # MAIL_SERVER = "smtp.office365.com"
    # MAIL_PORT = 587  # 465 for SSL, 587 for TLS
    # MAIL_USE_TLS = True
    # MAIL_USE_SSL = False
    # MAIL_USERNAME = os.getenv("EMAGRESER_MAIL_ADDRESS", "sirlene.torres35@hotmail.com")
    # MAIL_PASSWORD = os.getenv("EMAGRESER_MAIL_PASSWORD")
    # MAIL_DEFAULT_SENDER = "sirlene.torres35@hotmail.com"
    # SECURITY_EMAIL_SENDER = os.getenv("EMAGRESER_MAIL_ADDRESS", "sirlene.torres35@hotmail.com")
    # SECURITY_SEND_REGISTER_EMAIL = True
    # SECURITY_CONFIRMABLE = True
