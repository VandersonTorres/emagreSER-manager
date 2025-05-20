# 🩺 EmagreSER - Auriculotherapy Clinical Management Web App

**EmagreSER Manager** is a full-stack internal management system developed for a weight loss clinic. It streamlines operations for administrators, nutritionists, and secretaries with secure data handling, responsive design, and full CRUD functionality.

## 🔧 Tech Stack

- **Frontend**: HTML, CSS, JavaScript, Jinja2
- **Backend**: Python (Flask)
- **Database**: PostgreSQL/ Cloudinary
- **Deployment**: Heroku
- **Other**: PDF handling, WhatsApp/email integration, role-based access control

---

## 🖥️ Features

### 🔐 Role-Based Access
- Nutritionists can only view/edit their assigned patients, or if there was an appointment
- Only admins can manage system users
- Expired appointments remain available for historical searching

### 🧑‍⚕️ Patient Management
- Register, update, and delete patients, nutritionists, and diets
- Anthropometric and bioimpedance evaluation tracking, with auto-calc feature for BMI, Max/ Min / Ideal Weight, Daily Kcal/ Water ingesting and Nutritional Classification
- Historical charts showing patient progress

### 📅 Scheduling
- Book and cancel appointments
- View appointment history by date, even if expired

### 📝 Diet & PDF Handling
- In-browser diet PDF editing
- Send diets and reports via WhatsApp or email

### 📱 Responsive Design
- Fully usable on desktop and mobile devices
- Tables and views with filters for better user experience

---

## 🗂️ Screenshots

> ⚠️ Sensitive information has been blurred or redacted to protect privacy.

<!-- Insert censored screenshots here -->
![Dashboard View](screenshots/dashboard_blurred.png)
![Patient Profile](screenshots/patient_profile_blurred.png)
![Scheduling](screenshots/scheduling_blurred.png)

---

🚀 Deployment

> The app is deployed on Heroku and supports environment-based configuration. PostgreSQL is provisioned using Heroku add-ons.

## Installing

⚙️ Setup (Local)

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

The app should be accessible at http://127.0.0.1:5000.
