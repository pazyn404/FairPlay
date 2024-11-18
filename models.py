from hashlib import sha256
from secrets import token_hex

import numpy as np
from flask_login import UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.ext.hybrid import hybrid_property

from app import db
from games_configs import OptimalStoppingConfig
from utilities import secure_random


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    _password = db.Column("password", db.String(255), nullable=False)
    balance = db.Column(db.Integer, nullable=False, default=1000)

    @hybrid_property
    def password(self):
        return self._password

    @password.setter
    def password(self, password):
        self._password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self._password, password)


class BaseGame:
    __abstract__ = True

    OPEN_ATTRIBUTES = ["hashed_setup"]
    CLOSED_ATTRIBUTES = ["win", "hashed_setup", "salt"]

    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    bet = db.Column(db.Integer, nullable=False)
    salt = db.Column(db.String(255), nullable=False)
    game_over = db.Column(db.Boolean, nullable=False, default=False)
    win = db.Column(db.Boolean, default=None)

    @property
    def _game_setup(self):
        raise NotImplementedError

    @hybrid_property
    def hashed_setup(self):
        setup = f"{self._game_setup}:{self.salt}"
        hashed_setup = sha256(setup.encode()).hexdigest()

        return hashed_setup

    @classmethod
    def _generate_setup(cls):
        raise NotImplementedError

    @classmethod
    def create(cls, bet):
        user_id = current_user.id
        salt = token_hex(8)
        setup_params = cls._generate_setup()
        game = cls(user_id=user_id, salt=salt, bet=bet, **setup_params)

        db.session.add(game)
        db.session.commit()

        return game

    @classmethod
    def get(cls):
        game = cls.query.filter_by(user_id=current_user.id, game_over=False).first()

        return game

    def play(self, post_data):
        raise NotImplementedError

    def _win_condition(self, *args, **kwargs):
        raise NotImplementedError

    def open_data(self):
        return {attr: getattr(self, attr) for attr in self.__class__.OPEN_ATTRIBUTES}

    def closed_data(self):
        return {attr: getattr(self, attr) for attr in self.__class__.CLOSED_ATTRIBUTES}


class OptimalStoppingGame(db.Model, BaseGame):
    CONFIG = OptimalStoppingConfig
    OPEN_ATTRIBUTES = BaseGame.OPEN_ATTRIBUTES + ["revealed_numbers", "position", "numbers_count", "mean", "std_lower_bound", "std_upper_bound"]
    CLOSED_ATTRIBUTES = BaseGame.CLOSED_ATTRIBUTES + ["numbers", "position", "numbers_count", "mean", "std_lower_bound", "std_upper_bound", "seed", "std"]

    seed = db.Column(db.Integer(), nullable=False)
    position = db.Column(db.Integer(), nullable=False, default=0)
    std = db.Column(db.Integer(), nullable=False)
    mean = db.Column(db.Integer(), nullable=False, default=CONFIG.MEAN)
    std_lower_bound = db.Column(db.Integer(), nullable=False, default=CONFIG.STD_LOWER_BOUND)
    std_upper_bound = db.Column(db.Integer(), nullable=False, default=CONFIG.STD_UPPER_BOUND)
    numbers_count = db.Column(db.Integer(), nullable=False, default=CONFIG.NUMBERS_COUNT)

    @property
    def numbers(self):
        np.random.seed(self.seed)
        numbers = np.random.normal(self.mean, self.std, self.numbers_count).astype(int)

        return numbers

    @property
    def revealed_numbers(self):
        return self.numbers[:self.position + 1]

    @property
    def _game_setup(self):
        return f"{self.seed}:{self.std}"

    @classmethod
    def _generate_setup(cls):
        seed = secure_random(cls.CONFIG.SEED_LOWER_BOUND, cls.CONFIG.SEED_UPPER_BOUND)
        std = secure_random(cls.CONFIG.STD_LOWER_BOUND, cls.CONFIG.STD_UPPER_BOUND)

        return {"seed": seed, "std": std}

    def play(self, post_data):
        if not self._check_payload(post_data):
            return

        action = post_data.get("action")
        if action == "init":
            return
        elif action == "stop":
            position = self.position
            numbers = self.numbers

            self.win = self._win_condition(numbers, position)
            self.game_over = True
        elif action == "next":
            self.position += 1

        db.session.add(self)
        db.session.commit()

    def _check_payload(self, post_data):
        action = post_data.get("action")
        allowed_actions = ["init", "stop", "next"]
        if action not in allowed_actions:
            return False

        if action == "next" and self.position == self.CONFIG.NUMBERS_COUNT - 1:
            return False

        return True

    def _win_condition(self, numbers, position):
        return numbers[position] == max(numbers)
