IN PROGRESS...

INICIALIZAR O SERVIDOR FLASK:

flask --app app run

COMANDOS SQLITE:

rm -rf migrations               # Remove as migrações
rm database.db                  # Apaga o banco SQLite
flask db init                   # Inicia o banco
flask db migrate -m "Mensagem"  # Alterações no banco
flask db upgrade                # Recria o banco
