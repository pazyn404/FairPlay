from flask import render_template, redirect, request
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError

from app import app, db
from models import User, OptimalStoppingGame


GAMES_MODELS = {
    "optimal-stopping": OptimalStoppingGame
}


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    username = request.form.get("username")
    password = request.form.get("password")

    user = User(
        username=username,
        password=password
    )
    try:
        db.session.add(user)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return render_template("register.html", message="Account with this username already exists.")

    return render_template("register.html", message="Account has been created.")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username")
    password = request.form.get("password")

    user = User.query.filter_by(username=username).first()
    if not user:
        return render_template("login.html", message="Invalid username or password.")

    if user.check_password(password):
        login_user(user)
        return render_template("index.html", message="You are now logged in.")
    else:
        return render_template("login.html", message="Incorrect username or password.")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    logout_user()
    return render_template("index.html", message="You have been logged out.")


@app.route("/games", methods=["GET"])
@login_required
def games():
    return render_template("games.html")

@app.route("/play/<game_name>", methods=["GET", "POST"])
@login_required
def play(game_name):
    game_model = GAMES_MODELS.get(game_name)
    if not game_model:
        return render_template("games.html", message="Invalid game name.")

    template_name = f"{game_name.replace('-', '_')}.html"
    template_path = f"games/{template_name}"

    game = game_model.get()
    if request.method == "GET":
        if game:
            return render_template(template_path, **game.open_data())
        return render_template(template_path, active_game=False)

    if not game:
        bet = request.form.get("bet")
        if not bet.isnumeric() or not int(bet) > 0:
            return render_template(template_path, message="Invalid bet.", active_game=False)
        bet = int(bet)
        if current_user.balance < bet:
            return render_template(template_path, message="You don't have enough money.", active_game=False)

        game = game_model.create(bet)

        current_user.balance -= bet
        db.session.commit()

    game.play(request.form)
    if game.win:
        current_user.balance += 2 * game.bet
        db.session.commit()

    if not game.game_over:
        return render_template(template_path, **game.open_data(), active_game=True)
    else:
        massage = "You win." if game.win else "You lose."
        return render_template(template_path, message=massage, active_game=False)


@app.route("/statistics", methods=["GET"])
@login_required
def statistics():
    data = {}
    for game_name, game_model in GAMES_MODELS.items():
        data[game_name] = []
        completed_games = game_model.query.filter_by(user_id=current_user.id, game_over=True).all()
        for completed_game in completed_games:
            data[game_name].append(completed_game.closed_data())

    return render_template("statistics.html", data=data)
