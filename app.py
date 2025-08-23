import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import json
from datetime import datetime

# Initialize the Flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_super_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    subscription_type = db.Column(db.String(20), default='Free')
    profile_photo = db.Column(db.String(200), default='https://via.placeholder.com/150')
    bio = db.Column(db.Text, default='A new user on Quick4lio.')
    social_links = db.Column(db.Text, default='{}') # Stored as JSON string
    
    posts = db.relationship('Post', backref='author', lazy='dynamic')
    portfolio = db.relationship('Portfolio', backref='owner', uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content_text = db.Column(db.Text, nullable=False)
    content_image = db.Column(db.String(200)) # URL from Cloudinary
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    portfolio_type = db.Column(db.String(20), nullable=False, default='Free')
    sections_data = db.Column(db.Text, default='{}') # Stored as JSON string

# Create database tables
with app.app_context():
    db.create_all()

# Utility function for parsing JSON from database
def parse_json(data):
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return {}

# --- Routes ---

# Landing Page
@app.route('/')
def index():
    return render_template('index.html')

# Home Page with posts feed
@app.route('/feed')
def feed():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template('feed.html', posts=posts)

# User registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            flash('Username or Email already exists.', 'danger')
            return redirect(url_for('register'))

        new_user = User(username=username, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

# User login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

# User logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# User dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

# Create a new post
@app.route('/create-post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        content_text = request.form.get('content_text')
        content_image = request.form.get('content_image', None) 
        
        if not content_text:
            flash('Post content cannot be empty.', 'danger')
            return redirect(url_for('create_post'))

        new_post = Post(user_id=current_user.id, content_text=content_text, content_image=content_image)
        db.session.add(new_post)
        db.session.commit()
        flash('Post created successfully!', 'success')
        return redirect(url_for('feed'))
    return render_template('create_post.html')

# Profile page
@app.route('/user/<username>')
def user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = user.posts.order_by(Post.created_at.desc()).all()
    social_links = parse_json(user.social_links)
    return render_template('user_profile.html', user=user, posts=posts, social_links=social_links)

# Route to show plan details and comparison
@app.route('/plan-details')
@login_required
def plan_details():
    return render_template('plan_details.html', current_plan=current_user.subscription_type)

# Route to handle plan selection and payment
@app.route('/select-plan/<plan_type>')
@login_required
def select_plan(plan_type):
    if plan_type not in ['Free', 'Paid', 'Premium']:
        flash("Invalid plan selected.", "danger")
        return redirect(url_for('plan_details'))
        
    current_user.subscription_type = plan_type
    
    if current_user.portfolio:
        current_user.portfolio.portfolio_type = plan_type
    
    db.session.commit()
    
    flash(f'Your plan has been successfully updated to {plan_type}!', 'success')
    return redirect(url_for('dashboard'))

# Unified route to create/edit portfolio and save data
@app.route('/edit-portfolio', methods=['GET', 'POST'])
@login_required
def edit_portfolio():
    user_portfolio = current_user.portfolio

    if request.method == 'POST':
        portfolio_type = request.form.get('portfolio_type', 'Free')
        
        # Check if portfolio exists, if not, create one
        if not user_portfolio:
            user_portfolio = Portfolio(user_id=current_user.id, portfolio_type=portfolio_type, sections_data='{}')
            db.session.add(user_portfolio)
            db.session.commit()
        
        # Now we know a portfolio object exists
        user_portfolio.portfolio_type = portfolio_type
        
        data = {
            'header': {'name': request.form.get('name'), 'title': request.form.get('title')},
            'about': {'bio': request.form.get('bio')},
            'projects': [
                {'name': request.form.get('project_name_1'), 'desc': request.form.get('project_desc_1'), 'image': request.form.get('project_img_1')},
            ],
            'skills': request.form.get('skills').split(',') if request.form.get('skills') else [],
            'contact': {'email': request.form.get('contact_email'), 'phone': request.form.get('contact_phone')}
        }
        
        if portfolio_type in ['Paid', 'Premium']:
            data['paid_pages'] = {'home_content': request.form.get('home_content')}
        
        if portfolio_type == 'Premium':
            data['premium_pages'] = {
                'case_studies': request.form.get('case_studies'),
                'testimonials': request.form.get('testimonials'),
                'resume_link': request.form.get('resume_link'),
                'awards': request.form.get('awards')
            }
        
        user_portfolio.sections_data = json.dumps(data)
        db.session.commit()
        
        flash('Portfolio updated successfully!', 'success')
        return redirect(url_for('public_portfolio', username=current_user.username))
    
    # GET request to display the correct form
    plan = current_user.subscription_type
    
    # Ensure a portfolio exists before attempting to read its data
    if not user_portfolio:
        user_portfolio = Portfolio(user_id=current_user.id, portfolio_type=plan, sections_data='{}')
        db.session.add(user_portfolio)
        db.session.commit()
    
    sections_data = parse_json(user_portfolio.sections_data)
    
    if plan == 'Free':
        return render_template('edit_free_portfolio.html', sections_data=sections_data, portfolio=user_portfolio)
    elif plan == 'Paid':
        paid_pages = sections_data.get('paid_pages', {})
        return render_template('edit_paid_portfolio.html', sections_data=sections_data, portfolio=user_portfolio, paid_pages=paid_pages)
    elif plan == 'Premium':
        paid_pages = sections_data.get('paid_pages', {})
        premium_pages = sections_data.get('premium_pages', {})
        return render_template('edit_premium_portfolio.html', sections_data=sections_data, portfolio=user_portfolio, paid_pages=paid_pages, premium_pages=premium_pages)
    
    flash("Please select a plan first.", "warning")
    return redirect(url_for('plan_details'))

# Public portfolio page
@app.route('/p/<username>')
def public_portfolio(username):
    user = User.query.filter_by(username=username).first_or_404()
    portfolio = user.portfolio

    if not portfolio:
        return render_template('public_portfolio.html', user=user, portfolio=None)
    
    sections_data = parse_json(portfolio.sections_data)
    
    if portfolio.portfolio_type == 'Free':
        return render_template('free_portfolio.html', user=user, portfolio=portfolio, sections_data=sections_data)
    elif portfolio.portfolio_type == 'Paid':
        return render_template('paid_portfolio.html', user=user, portfolio=portfolio, sections_data=sections_data)
    elif portfolio.portfolio_type == 'Premium':
        return render_template('premium_portfolio.html', user=user, portfolio=portfolio, sections_data=sections_data)
    
    return render_template('public_portfolio.html', user=user, portfolio=None)

# To run the app:
if __name__ == '__main__':
    app.run(debug=True)
    