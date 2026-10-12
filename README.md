# Smart Parking System

SmartPark is a Flask-based parking management web application that
combines parking reservations, occupancy prediction, user accounts, and
parking analytics. It also includes experimental smart-parking features
such as dynamic pricing, slot recommendations, loyalty points,
waitlists, EV charging estimates, and simulated number-plate
recognition.

## Features

### User accounts and security

-   User registration with email OTP verification.
-   Login and logout with hashed passwords.
-   Password reset using an OTP and time-limited reset token.
-   Separate user and administrator access.
-   User profile and vehicle management.

### Parking operations

-   Browse parking lots and view slot availability.
-   Book parking slots and manage existing bookings.
-   Generate QR codes for bookings and support QR verification.
-   Extend a booking or check out early.
-   Purchase and manage parking passes.
-   View booking history and notifications.

### Prediction and analytics

-   Predict parking occupancy by lot, date, and time.
-   Compare four machine-learning models: Random Forest, Decision Tree,
    Linear Regression, and Support Vector Regression (SVM).
-   View model metrics and parking-related charts and analytics.
-   Admin tools for parking-lot management, model training, user
    management, and revenue reporting/export.

### Additional smart-parking features

-   Dynamic pricing based on estimated occupancy, time of day, and day
    of week.
-   Parking-slot recommendations based on slot scoring and preferences.
-   Loyalty tiers and reward-point calculations.
-   Group-booking planning.
-   In-memory waitlist with estimated waiting time.
-   EV charging time, energy, cost, and range estimates.
-   Carbon-savings estimates and per-user parking analytics.
-   Simulated vehicle number-plate recognition.

> **Note:** Some capabilities are simulations or estimates. In
> particular, number-plate recognition generates a sample plate rather
> than performing OCR on an actual image, and the occupancy model is
> trained on synthetic data. Treat predictions, pricing forecasts,
> charging calculations, and environmental estimates as demonstrative
> rather than production-grade guarantees.

## Technology stack

-   **Backend:** Python, Flask
-   **Database:** SQLite
-   **Machine learning:** scikit-learn, NumPy
-   **Security utilities:** Werkzeug password hashing
-   **QR codes and images:** `qrcode`, Pillow
-   **Messaging integrations:** SMTP email configuration and optional
    Twilio-related dependency
-   **Frontend:** Flask-rendered HTML templates (the template and static
    asset directories are required by the application but were not
    included in the supplied source files)

## Project structure

``` text
SmartPark/
├── app.py              # Flask routes, application logic, authentication, bookings and APIs
├── database.py         # SQLite connection, schema creation and demo data
├── ml_models.py        # Occupancy training, prediction and model metrics
├── new_features.py     # Pricing, recommendations, loyalty, waitlist, EV and analytics helpers
├── requirements.txt    # Python dependencies
├── templates/          # HTML templates required by render_template()
├── static/             # Frontend assets, if used by your copy of the project
└── data/               # Created at runtime; SQLite database and model metrics
```

## Requirements

-   Python 3.10 or newer is recommended.
-   `pip`
-   Internet access may be needed to install Python packages and to send
    email through an SMTP provider.

## Installation

1.  **Clone or download the project.** Place the Python files and
    `requirements.txt` in the same project directory.

2.  **Create and activate a virtual environment** (recommended).

    Windows PowerShell:

    ``` powershell
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    ```

    macOS/Linux:

    ``` bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install dependencies.**

    ``` bash
    pip install -r requirements.txt
    ```

4.  **Check the frontend files.** Make sure the project's `templates/`
    directory and the HTML files referenced by `render_template()` are
    present. The Python files alone are not a complete runnable web
    interface.

5.  **Configure email settings** if you want registration and
    password-reset OTPs delivered by email. Set these environment
    variables before launching the app:

    -   `EMAIL_HOST` --- SMTP server hostname (defaults to
        `smtp.gmail.com`)
    -   `EMAIL_PORT` --- SMTP port (defaults to `587`)
    -   `EMAIL_USER` --- SMTP account username
    -   `EMAIL_PASSWORD` --- SMTP password or provider-generated app
        password
    -   `EMAIL_FROM` --- sender address displayed in emails

    Example for Windows PowerShell (use your own values; do not commit
    credentials):

    ``` powershell
    $env:EMAIL_HOST = "smtp.gmail.com"
    $env:EMAIL_PORT = "587"
    $env:EMAIL_USER = "your-email@example.com"
    $env:EMAIL_PASSWORD = "your-app-password"
    $env:EMAIL_FROM = "SmartPark <your-email@example.com>"
    ```

    Equivalent environment-variable commands can be used on macOS/Linux.

## Run the application

From the project directory, run:

``` bash
python app.py
```

The application's entry point initializes the SQLite database, trains
the prediction models, and starts Flask on port `5000` in debug mode.
Once it starts, open:

``` text
http://127.0.0.1:5000
```

On first run, the database module creates `data/parking.db` and seeds
sample parking lots and demo accounts when the relevant tables are
empty. Model metrics may be written to `data/metrics.json`.

### Demo accounts

The database initialization code seeds these accounts when it
initializes an empty users table:

  Role            Username   Password
  --------------- ---------- ------------
  Administrator   `admin`    `admin123`
  Demo user       `demo`     `demo123`

Change or remove demo credentials before deploying anywhere accessible
to other people.

## Machine-learning models

SmartPark supports these regression models for estimating parking
occupancy:

-   **Random Forest**
-   **Decision Tree**
-   **Linear Regression**
-   **Support Vector Regression (SVM)**

The current implementation generates synthetic training examples based
on hour, weekday, month, holiday flag, and parking-lot ID. The displayed
model metrics are calculated against a held-out split of that generated
dataset. They should not be interpreted as validation against live
parking sensors or real-world historical data.

## Configuration and deployment notes

-   The Flask secret key is currently defined in `app.py`. Replace it
    with a strong secret supplied through an environment variable before
    deployment.
-   Do not store SMTP credentials or other secrets in source control. If
    real credentials have ever been committed, rotate them.
-   The application currently starts with `debug=True`; disable debug
    mode in production and use a production WSGI server.
-   Configure HTTPS, secure session-cookie settings, request/OTP rate
    limits, and suitable logging before exposing the application
    publicly.
-   The waitlist is stored in memory, so entries are not persistent
    across restarts and may not be shared across multiple application
    workers.
-   Use real parking data and validate model performance before relying
    on occupancy predictions for operational decisions.
-   Review payment-related workflows and integrate a real payment
    provider before treating payments as live transactions.

## Troubleshooting

-   **Missing template error:** Check that the required HTML files are
    in the `templates/` directory.
-   **Email OTP not arriving:** Verify the SMTP host, port, account, and
    app password. Check spam folders and SMTP provider restrictions.
-   **Dependency errors:** Activate the intended virtual environment and
    run `pip install -r requirements.txt` again.
-   **Database issues:** Stop the application and back up
    `data/parking.db` before attempting any database reset or manual
    changes.
-   **Slow first startup:** Model training runs when the application
    starts and may take a little time.

## License

This project is developed for educational and learning purposes. 

## Author

Mankar Kishore Babu
