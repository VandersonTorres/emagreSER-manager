import getpass
import uuid

from flask_security.utils import hash_password

from app import create_app, db
from app.models import Role, User

# Execute from the root of the project
# python -m scripts.create_user

app = create_app()


def input_with_confirmation(prompt: str, password: bool = False) -> str:
    while True:
        if not password:
            value = input(prompt)
            confirmation = input(f"Received '{value}'. It it correct? (y/n): ")
            if confirmation.lower() == "y":
                return value
            print(f"Input '{value}' rejected. Please try again.")
        else:
            value = getpass.getpass(prompt)
            confirmation = getpass.getpass("Repeat the password to confirm: ")
            if value == confirmation:
                return value
            print("Passwords do not match. Please try again.")


with app.app_context():
    email = input_with_confirmation("Enter the email address for the user: ")
    password = input_with_confirmation("Enter the password for the user: ", password=True)
    role = input("Should this be an admin user? (y/n): ").lower() == "y"
    if role:
        # Check if the role already exists, otherwise create it
        admin_role = Role.query.filter_by(name="admin").first()
        if not admin_role:
            admin_role = Role(name="admin")
            db.session.add(admin_role)
            db.session.commit()
            print("Created 'admin' role.")

    # Check if the user already exists
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        print("User already exists.")
    else:
        # Create the initial admin user
        user = User(email=email, active=True, password=hash_password(password), fs_uniquifier=uuid.uuid4().hex)
        if role:
            user.roles.append(admin_role)  # Assign the 'admin' role to the user

        db.session.add(user)
        db.session.commit()
        print(f"User {email} created successfully{' with admin role.' if role else '.'}")
