# emagreSER-manager
Management tools for emagreSer - Slimming and Auriculotherapy Clinic

## Installing

- Clone this repository to a local environment;

- Create virtual environment:
```bash
$ python -m venv .venv
```

- Activate the virtual environment
```bash
$ source .venv/bin/activate
```

- Install dependencies from `requirements.txt`, the project dependencies are already included there. Run into the terminal:
```bash
$ pip install -r requirements.txt
```

- Install pre-commit
```bash
$ pip install pre-commit
$ pre-commit install
```

## Running the project

- Inside the `/app` folder run the command to start the flask app

```bash
$ flask --app app run
```

The app should be accessible at http://127.0.0.1:5000. You will be able to login in there.

- *You will need to ask for an user account to the admin (as detailed in the initial page).*
