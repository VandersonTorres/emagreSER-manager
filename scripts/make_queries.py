from app import create_app
from app.models import Diet, Pacients, Schedules, User  # noqa

# EXECUÇÃO
# python -m scripts.make_queries

app = create_app()

with app.app_context():
    users = User.query.all()
    print("USERS:")
    for user in users:
        print(user.email)

    pacients = Pacients.query.all()
    print("PACIENTS:")
    for pacient in pacients:
        print(pacient)

    diets = Diet.query.all()
    print("DIETS:")
    for diet in diets:
        print(diet)

    schedules = Schedules.query.all()
    print("SCHEDULES:")
    for schedule in schedules:
        print(schedule)

"""
COMANDO PARA VERIFICAR COLUNAS:
    $ sqlite3 <path_do_db.db> "PRAGMA table_info(<nome-da-tabela>);"

COMANDO PARA ADICIONAR NOVA COLUNA:
    $ sqlite3 <path_do_db.db> "ALTER TABLE <nome-da-tabela> ADD COLUMN <nome-da-coluna> TEXT DEFAULT <'nome-default'>;"
"""
