from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# 1. User Table
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=True) # Validated later
    password_hash = db.Column(db.String(150), nullable=False)
    leetcode_username = db.Column(db.String(150), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_verified = db.Column(db.Boolean, default=False)
    verification_otp = db.Column(db.String(6), nullable=True)
    
    # Streak & Activity Tracking
    last_active_date = db.Column(db.Date, nullable=True)
    last_submission_timestamp = db.Column(db.DateTime, nullable=True)
    last_leetcode_sync = db.Column(db.DateTime, nullable=True)
    streak_count = db.Column(db.Integer, default=0)
    
    # Relationship to track progress
    progress = db.relationship('UserProgress', backref='user', lazy=True)

    def set_password(self, password):
        # Use pbkdf2:sha256 to ensure hash fits in 150 chars (defaults to scrypt which is longer)
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# 2. Question Table (The static DSA data)
class Question(db.Model):
    __tablename__ = 'dsa_questions'  # <--- FIX: Points to your existing SQL table
    
    id = db.Column(db.Integer, primary_key=True)
    problem_name = db.Column(db.String(255))
    topic = db.Column(db.String(100))
    difficulty = db.Column(db.String(50))
    problem_link = db.Column(db.Text)
    editorial_link = db.Column(db.Text)
    week = db.Column(db.Integer)

# 3. UserProgress Table (Links User <-> Question)
class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # FIX: Points to the 'dsa_questions' table explicitly
    question_id = db.Column(db.Integer, db.ForeignKey('dsa_questions.id'), nullable=False)
    
    is_solved = db.Column(db.Boolean, default=False)
    is_bookmarked = db.Column(db.Boolean, default=False)