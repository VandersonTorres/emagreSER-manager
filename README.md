IN PROGRESS...

INICIALIZAR O SERVIDOR FLASK:

flask --app app run

COMANDOS SQLITE:

flask db migrate -m "Mensagem"  # Alterações no banco
rm -f instance/app.db           # Apaga o banco SQLite
flask db upgrade                # Recria o banco
