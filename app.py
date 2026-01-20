import os
import random
import requests
from functools import wraps
from datetime import date, timedelta
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, abort, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from models import db, User, Question, UserProgress
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-for-production'

# --- Mail Config ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465  # Changed to 465
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True # Use SSL instead of TLS
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_USER')
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASS')
mail = Mail(app)

# --- Database Config ---
# Uses the URL from .env (Postgres) if available, otherwise falls back to local SQLite
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI') or f'sqlite:///{os.path.join(BASE_DIR, "dsa.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# --- Security: Prevent Caching ---
# This ensures that when you logout, the back button doesn't show sensitive pages
# and different browsers don't show cached versions of the dashboard.
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

# --- Login Setup ---
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("You do not have permission to access that page.", "error")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_verified:
                flash('Please verify your email first.', 'warning')
                session['user_id_to_verify'] = user.id
                return redirect(url_for('verify_otp'))
                
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Username or Email already exists', 'error')
        else:
            otp = str(random.randint(100000, 999999))
            
            new_user = User(username=username, email=email, is_verified=False, verification_otp=otp)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            
            # Send Email
            try:
                # Only attempt to send if credentials are set
                if app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
                    msg = Message('Verify your DSA Tracker Account', sender=app.config['MAIL_USERNAME'], recipients=[email])
                    msg.body = f'Your verification OTP is: {otp}'
                    
                    # Send synchronously for Vercel
                    mail.send(msg)
                    flash('Account created! Please check your email for the OTP.', 'info')
                else:
                     flash('Account created! Check console for OTP (Email not configured).', 'warning')
                     print(f"DEV MODE OTP: {otp}")

            except Exception as e:
                print(f"Mail Error: {e}")
                # Log the OTP to Vercel logs just in case email fails
                print(f"FALLBACK OTP: {otp}") 
                flash(f'Error sending email. Please check logs.', 'warning')
            
            session['user_id_to_verify'] = new_user.id
            return redirect(url_for('verify_otp'))
            
    return render_template('register.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify_otp():
    if 'user_id_to_verify' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        otp_input = request.form.get('otp')
        user_id = session.get('user_id_to_verify')
        user = User.query.get(user_id)
        
        if user and user.verification_otp == otp_input:
            user.is_verified = True
            user.verification_otp = None
            db.session.commit()
            session.pop('user_id_to_verify', None)
            login_user(user)
            flash('Email verified successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid OTP. Please try again.', 'error')
            
    return render_template('verify.html')

@app.route('/profile')
@login_required
def profile():
    # Get all questions
    all_qs = Question.query.all()
    # Get all progress
    all_prog = UserProgress.query.filter_by(user_id=current_user.id).all()
    solved_ids = {p.question_id for p in all_prog if p.is_solved}

    stats = {
        'completed': len(solved_ids),
        'total': len(all_qs),
        'percent': 0,
        'difficulty_breakdown': {
            'Easy': {'completed': 0, 'total': 0},
            'Medium': {'completed': 0, 'total': 0},
            'Hard': {'completed': 0, 'total': 0}
        }
    }
    
    if stats['total'] > 0:
        stats['percent'] = int((stats['completed'] / stats['total']) * 100)

    for q in all_qs:
        d_key = 'Hard' # Default
        if 'Easy' in q.difficulty: d_key = 'Easy'
        elif 'Medium' in q.difficulty: d_key = 'Medium'
        
        if d_key in stats['difficulty_breakdown']:
            stats['difficulty_breakdown'][d_key]['total'] += 1
            if q.id in solved_ids:
                stats['difficulty_breakdown'][d_key]['completed'] += 1

    return render_template('profile.html', stats=stats)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/update_leetcode_username', methods=['POST'])
@login_required
def update_leetcode_username():
    new_username = request.form.get('leetcode_username')
    if new_username:
        current_user.leetcode_username = new_username.strip()
        db.session.commit()
        flash('LeetCode username updated!', 'success')
    else:
        # If empty allowed to clear
        if new_username == "":
             current_user.leetcode_username = None
             db.session.commit()
             flash('LeetCode username removed.', 'info')
        else:
             flash('Please enter a username.', 'warning')
    return redirect(url_for('profile'))

@app.route('/sync_leetcode', methods=['POST'])
@login_required
def sync_leetcode():
    username = current_user.leetcode_username
    if not username:
        flash('Please set your LeetCode username first.', 'warning')
        return redirect(url_for('profile'))

    # GraphQL Query
    query = """
    query recentAcSubmissions($username: String!, $limit: Int!) {
      recentAcSubmissionList(username: $username, limit: $limit) {
        titleSlug
      }
    }
    """
    
    variables = {
        "username": username,
        "limit": 100 
    }

    try:
        resp = requests.post(
            'https://leetcode.com/graphql',
            json={'query': query, 'variables': variables},
            timeout=10
        )
        data = resp.json()
        
        if 'errors' in data:
             flash(f'LeetCode API Error: {data["errors"][0]["message"]}', 'error')
             return redirect(url_for('profile'))

        submissions = data.get('data', {}).get('recentAcSubmissionList', [])
        solved_slugs = {sub['titleSlug'] for sub in submissions}

        if not solved_slugs:
            flash('No recent submissions found or user not found.', 'info')
            return redirect(url_for('profile'))

        # Check against Question DB
        all_qs = Question.query.all()
        marked_count = 0
        
        for q in all_qs:
            if not q.problem_link: continue
            
            # Extract slug from problem_link
            # Typical link: https://leetcode.com/problems/two-sum/
            parts = q.problem_link.strip('/').split('/')
            q_slug = parts[-1] 
            
            if q_slug in solved_slugs:
                # Mark as solved
                prog = UserProgress.query.filter_by(user_id=current_user.id, question_id=q.id).first()
                if not prog:
                    prog = UserProgress(user_id=current_user.id, question_id=q.id, is_solved=True)
                    db.session.add(prog)
                    marked_count += 1
                elif not prog.is_solved:
                    prog.is_solved = True
                    marked_count += 1
        
        if marked_count > 0:
            db.session.commit()
            # Update streak if we have that function available
            try:
                update_streak(current_user)
            except:
                pass 
            flash(f'Synced! Marked {marked_count} problems as solved.', 'success')
        else:
            flash('Synced! No new problems found in your recent history.', 'info')

    except Exception as e:
        print(f"Sync Error: {e}")
        flash('Failed to connect to LeetCode.', 'error')

    return redirect(url_for('profile'))

# --- Helper Functions ---

def update_streak(user):
    """Updates user streak based on activity date."""
    today = date.today()
    
    # If already active today, do nothing
    if user.last_active_date == today:
        return

    # If active yesterday, increment streak
    if user.last_active_date == today - timedelta(days=1):
        user.streak_count = (user.streak_count or 0) + 1
    else:
        # Otherwise reset streak to 1
        user.streak_count = 1
    
    user.last_active_date = today
    # Note: We don't commit here, we let the caller handle commits to keep transaction atomic

@app.route('/dashboard')
@login_required
def dashboard():
    # Fetch all questions ordered by week
    all_questions = Question.query.order_by(Question.week, Question.id).all()
    
    # Fetch user's progress
    progress_records = UserProgress.query.filter_by(user_id=current_user.id).all()
    
    # Create lookup dictionaries for fast access in template
    solved_map = {p.question_id: p.is_solved for p in progress_records}
    bookmark_map = {p.question_id: p.is_bookmarked for p in progress_records}
    
    # Calculate XP (100 XP per solved problem)
    solved_count = sum(1 for p in progress_records if p.is_solved)
    user_xp = solved_count * 100
    
    # Organize by week for the accordion view
    weeks_data = {}
    weeks_stats = {} # To store progress per week
    
    for i in range(1, 15):
        weeks_data[i] = []
        weeks_stats[i] = {'total': 0, 'completed': 0, 'percent': 0}
        
    for q in all_questions:
        if q.week in weeks_data:
            is_solved = solved_map.get(q.id, False)
            weeks_data[q.week].append({
                'q': q,
                'solved': is_solved,
                'bookmarked': bookmark_map.get(q.id, False)
            })
            
            # Update stats
            weeks_stats[q.week]['total'] += 1
            if is_solved:
                weeks_stats[q.week]['completed'] += 1
                
    # Calculate percentages
    for w in weeks_stats:
        if weeks_stats[w]['total'] > 0:
            weeks_stats[w]['percent'] = int((weeks_stats[w]['completed'] / weeks_stats[w]['total']) * 100)

    return render_template('dashboard.html', 
                         weeks=weeks_data, 
                         weeks_stats=weeks_stats,
                         user_xp=user_xp,
                         username=current_user.username)

@app.route('/revision')
@login_required
def revision():
    # Fetch user's bookmarked progress
    bookmarks = UserProgress.query.filter_by(user_id=current_user.id, is_bookmarked=True).all()
    
    # Get the question IDs
    bookmarked_ids = [b.question_id for b in bookmarks]
    
    # Fetch the actual questions (using IN clause for efficiency)
    if bookmarked_ids:
        questions = Question.query.filter(Question.id.in_(bookmarked_ids)).all()
    else:
        questions = []
        
    # Create a nice list of dicts to pass to template
    # We map back to find the 'solved' status for these bookmarked questions
    # (Since we already have the progress objects in 'bookmarks', we can map them)
    progress_map = {b.question_id: b for b in bookmarks}
    
    revision_data = []
    for q in questions:
        prog = progress_map.get(q.id)
        revision_data.append({
            'question': q,
            'solved': prog.is_solved if prog else False
        })
    
    return render_template('revision.html', questions=revision_data)

# --- API Endpoints (AJAX) ---

@app.route('/api/toggle', methods=['POST'])
@login_required
def toggle_status():
    data = request.json
    q_id = data.get('question_id')
    field = data.get('field') # 'solved' or 'bookmarked'
    set_to_solved = data.get('set_to_solved') # Optional boolean from frontend

    progress = UserProgress.query.filter_by(user_id=current_user.id, question_id=q_id).first()
    
    if not progress:
        progress = UserProgress(user_id=current_user.id, question_id=q_id)
        db.session.add(progress)
    
    if field == 'solved':
        # If frontend sent explicit state (true/false), use it. Else toggle.
        if set_to_solved is not None:
             progress.is_solved = set_to_solved
        else:
             progress.is_solved = not progress.is_solved
             
        new_val = progress.is_solved
        
        # Update streak if problem is solved
        if new_val:
             update_streak(current_user)

    elif field == 'bookmarked':
        progress.is_bookmarked = not progress.is_bookmarked
        new_val = progress.is_bookmarked
        
    db.session.commit()
    
    # --- Calculate Updated Stats for Live UI ---
    
    # 1. XP
    solved_count_all = UserProgress.query.filter_by(user_id=current_user.id, is_solved=True).count()
    new_xp = solved_count_all * 100
    
    # 2. Streak
    new_streak = current_user.streak_count
    
    # 3. Week Stats (if solved changed)
    week_data = None
    if field == 'solved':
        question = db.session.get(Question, q_id)
        if question:
            week_num = question.week
            total_week = Question.query.filter_by(week=week_num).count()
            
            # Count user solved for this week
            completed_week = db.session.query(UserProgress).join(Question).filter(
                UserProgress.user_id == current_user.id,
                UserProgress.is_solved == True,
                Question.week == week_num
            ).count()
            
            percent = int((completed_week / total_week) * 100) if total_week > 0 else 0
            
            week_data = {
                'week': week_num,
                'completed': completed_week,
                'total': total_week,
                'percent': percent
            }

    return jsonify({
        'success': True, 
        'new_value': new_val,
        'new_xp': new_xp,
        'new_streak': new_streak,
        'week_data': week_data
    })

@app.route('/api/random', methods=['GET'])
@login_required
def random_question():
    mode = request.args.get('mode', 'any') # 'any' or 'unsolved'
    
    if mode == 'unsolved':
        # Subquery to find solved IDs
        solved_ids = db.session.query(UserProgress.question_id).filter_by(user_id=current_user.id, is_solved=True)
        # Filter questions NOT in solved_ids
        candidates = Question.query.filter(Question.id.notin_(solved_ids)).all()
    else:
        candidates = Question.query.all()
        
    if not candidates:
        return jsonify({'error': 'No questions found!'})
        
    picked = random.choice(candidates)
    
    # Check progress
    progress = UserProgress.query.filter_by(user_id=current_user.id, question_id=picked.id).first()
    is_solved = progress.is_solved if progress else False
    is_bookmarked = progress.is_bookmarked if progress else False

    return jsonify({
        'id': picked.id,
        'name': picked.problem_name,
        'link': picked.problem_link,
        'topic': picked.topic,
        'difficulty': picked.difficulty,
        'week': picked.week,
        'solved': is_solved,
        'bookmarked': is_bookmarked
    })

# --- Admin Routes ---

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    stats = {
        'user_count': User.query.count(),
        'question_count': Question.query.count(),
        'progress_count': UserProgress.query.count()
    }
    users = User.query.all()
    return render_template('admin.html', stats=stats, users=users)

@app.route('/admin/add_question', methods=['POST'])
@login_required
@admin_required
def admin_add_question():
    try:
        new_q = Question(
            problem_name=request.form.get('problem_name'),
            topic=request.form.get('topic'),
            difficulty=request.form.get('difficulty'),
            problem_link=request.form.get('problem_link'),
            editorial_link=request.form.get('editorial_link'),
            week=int(request.form.get('week'))
        )
        db.session.add(new_q)
        db.session.commit()
        flash('Question added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding question: {str(e)}', 'error')
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Cannot delete an admin user via this interface.', 'error')
        return redirect(url_for('admin_dashboard'))
        
    try:
        # Delete related progress first (though cascade might handle it if set up, manual is safer here without checking model extensively)
        UserProgress.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.username} deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'error')
        
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # Creates tables if they don't exist
    app.run(debug=True)