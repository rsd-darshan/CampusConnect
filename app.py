from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from openai_api import get_university_recommendations 
from flask_socketio import SocketIO, send, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
import os
from flask import g
from flask import flash
from werkzeug.utils import secure_filename
from datetime import datetime
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///advanced_platform.db'  # Update with your database URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/videos'
app.config['UPLOAD_FOLDER'] = 'static/reels'
app.secret_key = 'super_secret_key'


db = SQLAlchemy(app)
migrate = Migrate(app, db)
socketio = SocketIO(app)

friends = db.Table('friends',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('friend_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    profile_pic = db.Column(db.String(120), nullable=True)
    password_hash = db.Column(db.String(128))
    
    # New GPA fields for classes 9 to 12
    gpa_class_9 = db.Column(db.String(5), nullable=True)
    gpa_class_10 = db.Column(db.String(5), nullable=True)
    gpa_class_11 = db.Column(db.String(5), nullable=True)
    gpa_class_12 = db.Column(db.String(5), nullable=True)
    
    # Existing fields
    sat_score = db.Column(db.String(10), nullable=True)
    gpa = db.Column(db.String(5), nullable=True)
    eca = db.Column(db.String(120), nullable=True)
    essay = db.Column(db.Text, nullable=True)
    
    # New fields for university status
    universities_to_apply = db.Column(db.Text, nullable=True)  # Comma-separated list of universities
    universities_applied = db.Column(db.Text, nullable=True)   # Comma-separated list of universities
    universities_studying = db.Column(db.String(120), nullable=True)  # Currently studying at

    # New fields for Major and Minor
    major_subject = db.Column(db.String(100), nullable=True)
    minor_subject = db.Column(db.String(100), nullable=True)

    stars_received = db.Column(db.Integer, default=0)

    # Adding the friends relationship
    friends = db.relationship(
        'User', 
        secondary=friends,
        primaryjoin=(friends.c.user_id == id),
        secondaryjoin=(friends.c.friend_id == id),
        backref=db.backref('user_friends', lazy='dynamic'),
        lazy='dynamic'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_friends_with(self, user):
        return user in self.friends





class Star(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    giver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # The user who gives the star
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # The user who receives the star

    giver = db.relationship('User', foreign_keys=[giver_id], backref='given_stars')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_stars')


class HelperRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    helper_type = db.Column(db.String(20), nullable=False)  # 'lor' or 'counsel'
    status = db.Column(db.String(20), nullable=False, default='pending')  # 'pending', 'accepted', 'declined'

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_helper_requests')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_helper_requests')


# Reel Model (SQLAlchemy)
class Reel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    filename = db.Column(db.String(120), nullable=False)

# Moved `db.create_all()` to the correct place inside the app context

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    filename = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    tags = db.Column(db.String(120), nullable=True)
    thumbnail = db.Column(db.String(120), nullable=True)
    privacy = db.Column(db.String(50), nullable=False, default='public')
    uploader_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    approved = db.Column(db.Boolean, default=False)
    uploader = db.relationship('User', backref=db.backref('videos', lazy=True))


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'))

    user = db.relationship('User', backref='messages')
    group = db.relationship('Group', backref='messages')

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    members = db.relationship('User', secondary='group_members', backref='groups')

# Association table for Group members
group_members = db.Table('group_members',
    db.Column('group_id', db.Integer, db.ForeignKey('group.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)


class Reaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    reaction_type = db.Column(db.String(20))  # 'like', 'love', 'haha', 'wow', 'sad', 'angry'

    user = db.relationship('User', backref=db.backref('reactions', lazy=True))
    video = db.relationship('Video', backref=db.backref('reactions', lazy=True))

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.Text, nullable=False)
    
    video = db.relationship('Video', backref=db.backref('comments', lazy=True))
    user = db.relationship('User', backref=db.backref('comments', lazy=True))

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    message = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, default=False)


class PrivateMessage(db.Model):
    __tablename__ = 'private_message'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_private_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_private_messages')




class VideoAnalytics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'))
    views = db.Column(db.Integer, default=0)
    likes = db.Column(db.Integer, default=0)
    comments = db.Column(db.Integer, default=0)

class FriendRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')  # Default to 'pending'

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_requests')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_requests')


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)

    user = db.relationship('User', backref=db.backref('posts', lazy=True))


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, nullable=False)

# Chat rooms and users tracking
users_in_rooms = {}



# Routes
@app.route('/')
def index():
    return render_template('index.html')

# Example: Register a new user
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Check if the email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return 'Email already exists. Please choose a different email.'

        # Check if the username already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return 'Username already exists. Please choose a different username.'

        # Create and save the new user
        new_user = User(username=username, email=email)
        new_user.set_password(password)  # Hash the password
        db.session.add(new_user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return 'An error occurred while trying to register. Please try again.'

        session['username'] = username
        session['friends'] = []  # Initialize friends list as empty for a new user
        return redirect(url_for('public_feed'))

    return render_template('register.html')




@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['username'] = username
            session['friends'] = [friend.username for friend in user.friends]  # Initialize friends list in session
            return redirect(url_for('public_feed'))  # Redirect to public feed instead of dashboard
        else:
            return 'Invalid credentials'
    return render_template('login.html')



@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'username' in session:
        user = User.query.filter_by(username=session['username']).first()
        if request.method == 'POST':
            user.sat_score = request.form['sat_score']
            user.gpa = request.form['gpa']
            user.eca = request.form['eca']
            user.essay = request.form['essay']
            user.major_subject = request.form['major_subject']  # New field for Major
            user.minor_subject = request.form['minor_subject']  # New field for Minor
            
            # Handle profile picture upload
            if 'profile_pic' in request.files:
                profile_pic = request.files['profile_pic']
                if profile_pic:
                    filename = secure_filename(profile_pic.filename)
                    profile_pic.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    user.profile_pic = filename
            
            db.session.commit()  # Save all updates to the database
            return redirect(url_for('profile'))
        
        return render_template('profile.html', user=user)
    return redirect(url_for('login'))





@app.route('/like_video/<int:video_id>', methods=['POST'])
def like_video(video_id):
    if 'username' not in session:
        return 'Unauthorized', 401
    
    user = User.query.filter_by(username=session['username']).first()
    video = Video.query.get_or_404(video_id)

    existing_reaction = Reaction.query.filter_by(video_id=video_id, user_id=user.id, reaction_type='like').first()
    
    if not existing_reaction:
        new_reaction = Reaction(video_id=video_id, user_id=user.id, reaction_type='like')
        db.session.add(new_reaction)
        db.session.commit()
    
    return 'Liked', 200





def get_current_user():
    if 'username' in session:
        return User.query.filter_by(username=session['username']).first()
    return None

@app.before_request
def before_request():
    g.current_user = get_current_user()




@app.route('/send_friend_request/<int:receiver_id>', methods=['POST'])
def send_friend_request(receiver_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    sender = User.query.filter_by(username=session['username']).first()
    receiver = User.query.get(receiver_id)

    if receiver and receiver != sender:
        existing_request = FriendRequest.query.filter_by(sender_id=sender.id, receiver_id=receiver.id).first()
        if not existing_request:
            friend_request = FriendRequest(sender_id=sender.id, receiver_id=receiver.id, status='pending')
            db.session.add(friend_request)
            db.session.commit()
            return f'Friend request sent to {receiver.username}!'
        else:
            return 'Friend request already sent.'
    
    return redirect(url_for('view_profile', user_id=receiver_id))

@app.route('/remove_friend/<int:friend_id>', methods=['POST'])
def remove_friend(friend_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    friend = User.query.get(friend_id)

    if not user or not friend:
        return redirect(url_for('friend_list'))

    # Remove the friend relationship
    if friend in user.friends:
        user.friends.remove(friend)
        friend.friends.remove(user)
        db.session.commit()

    return redirect(url_for('friend_list'))




@app.route('/give_star/<int:receiver_id>', methods=['POST'])
def give_star(receiver_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    current_user = User.query.filter_by(username=session['username']).first()
    receiver = User.query.get(receiver_id)

    # Check if the current user has already given a star to the receiver
    existing_star = Star.query.filter_by(giver_id=current_user.id, receiver_id=receiver.id).first()
    if existing_star:
        return jsonify({'status': 'already_given'}), 400  # Error: Already gave a star to this user

    # Add a new star
    receiver.stars_received += 1
    new_star = Star(giver_id=current_user.id, receiver_id=receiver.id)
    db.session.add(new_star)
    db.session.commit()

    return jsonify({'status': 'success'}), 200  # Success: Star given


@app.route('/create_group', methods=['POST'])
def create_group():
    if 'username' not in session:
        return redirect(url_for('login'))

    group_name = request.form.get('group_name')
    user = User.query.filter_by(username=session['username']).first()

    if group_name and user:
        new_group = Group(name=group_name)
        new_group.members.append(user)  # Add the creator to the group
        db.session.add(new_group)
        db.session.commit()
        return redirect(url_for('chat'))
    else:
        return "Error creating group", 400


@app.route('/remove_member_from_group', methods=['POST'])
def remove_member_from_group():
    data = request.json
    group_id = data.get('group_id')
    user_id = data.get('user_id')
    group = Group.query.get_or_404(group_id)
    user = User.query.get_or_404(user_id)
    if user in group.members:
        group.members.remove(user)
        db.session.commit()
        return '', 200
    return '', 400

# Route to send a request for LOR
@app.route('/request_lor/<int:receiver_id>', methods=['POST'])
def request_lor(receiver_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    sender = User.query.filter_by(username=session['username']).first()
    receiver = User.query.get(receiver_id)

    if not receiver or receiver == sender:
        return redirect(url_for('search'))

    # Check if the LOR request already exists
    existing_request = HelperRequest.query.filter_by(sender_id=sender.id, receiver_id=receiver.id, helper_type='lor').first()
    if not existing_request:
        # Create a new LOR request
        new_request = HelperRequest(sender_id=sender.id, receiver_id=receiver.id, helper_type='lor', status='pending')
        db.session.add(new_request)
        db.session.commit()
        return f'LOR request sent to {receiver.username}!'
    else:
        return 'LOR request already sent.'

# Route to send a request for Counsel
@app.route('/request_counsel/<int:receiver_id>', methods=['POST'])
def request_counsel(receiver_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    sender = User.query.filter_by(username=session['username']).first()
    receiver = User.query.get(receiver_id)

    if not receiver or receiver == sender:
        return redirect(url_for('search'))

    # Check if the Counsel request already exists
    existing_request = HelperRequest.query.filter_by(sender_id=sender.id, receiver_id=receiver.id, helper_type='counsel').first()
    if not existing_request:
        # Create a new Counsel request
        new_request = HelperRequest(sender_id=sender.id, receiver_id=receiver.id, helper_type='counsel', status='pending')
        db.session.add(new_request)
        db.session.commit()
        return f'Counsel request sent to {receiver.username}!'
    else:
        return 'Counsel request already sent.'

@app.route('/ai_search', methods=['GET', 'POST'])
def ai_search():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()

    # Initialize flags for rendering template
    manual_input = False
    results = None

    if request.method == 'POST':
        if 'search_current_profile' in request.form:
            # Generate a profile summary from the user's current data
            profile_summary = (
                f"User has a GPA of {user.gpa or 'not provided'}, "
                f"SAT score of {user.sat_score or 'not provided'}, "
                f"is majoring in {user.major_subject or 'not specified'} and minoring in {user.minor_subject or 'not specified'}, "
                f"and is involved in the following extracurricular activities: {user.eca or 'none'}."
            )
            # Call the function to get university recommendations
            results = get_university_recommendations(profile_summary)
            results = results.replace('\n', '<br>')  # Format for HTML display

        elif 'manual_input' in request.form:
            # Set flag to show manual input form
            manual_input = True

        elif 'submit_manual_input' in request.form:
            # Collect data from manual input form
            gpa = request.form['gpa']
            sat_score = request.form['sat_score']
            eca = request.form['eca']
            essay = request.form['essay']
            major = request.form['major']
            minor = request.form['minor']
            
            # Generate a profile summary from the manual input
            profile_summary = (
                f"User has a GPA of {gpa}, SAT score of {sat_score}, "
                f"is majoring in {major} and minoring in {minor}, "
                f"and is involved in the following extracurricular activities: {eca}."
            )
            # Call the function to get university recommendations
            results = get_university_recommendations(profile_summary)
            results = results.replace('\n', '<br>')  # Format for HTML display

    return render_template('ai_search.html', user=user, results=results, manual_input=manual_input)






# Route to view received LOR and Counsel requests
@app.route('/helpers_section')
def helpers_section():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()

    # Fetch received requests for LOR and Counsel
    lor_requests = HelperRequest.query.filter_by(receiver_id=user.id, helper_type='lor', status='pending').all()
    counsel_requests = HelperRequest.query.filter_by(receiver_id=user.id, helper_type='counsel', status='pending').all()

    return render_template('helpers_section.html', lor_requests=lor_requests, counsel_requests=counsel_requests)

# Route to handle response to LOR or Counsel requests
@app.route('/respond_helper_request/<int:request_id>/<response>', methods=['POST'])
def respond_helper_request(request_id, response):
    if 'username' not in session:
        return redirect(url_for('login'))

    helper_request = HelperRequest.query.get_or_404(request_id)
    
    if response == 'accept':
        helper_request.status = 'accepted'
    else:
        helper_request.status = 'declined'

    db.session.commit()
    return redirect(url_for('helpers_section'))




@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()

    if request.method == 'POST':
        user.username = request.form['username']
        user.email = request.form['email']
        user.gpa_class_9 = request.form.get('gpa_class_9', user.gpa_class_9)
        user.gpa_class_10 = request.form.get('gpa_class_10', user.gpa_class_10)
        user.gpa_class_11 = request.form.get('gpa_class_11', user.gpa_class_11)
        user.gpa_class_12 = request.form.get('gpa_class_12', user.gpa_class_12)
        user.sat_score = request.form.get('sat_score', user.sat_score)
        user.eca = request.form.get('eca', user.eca)
        user.essay = request.form.get('essay', user.essay)
        user.universities_to_apply = request.form.get('universities_to_apply', user.universities_to_apply)
        user.universities_applied = request.form.get('universities_applied', user.universities_applied)
        user.universities_studying = request.form.get('universities_studying', user.universities_studying)
        user.major_subject = request.form.get('major_subject', user.major_subject)
        user.minor_subject = request.form.get('minor_subject', user.minor_subject)
        
        # Handle profile picture upload
        if 'profile_pic' in request.files:
            profile_pic = request.files['profile_pic']
            if profile_pic:
                filename = secure_filename(profile_pic.filename)
                profile_pic.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                user.profile_pic = filename
        
        db.session.commit()
        return redirect(url_for('profile'))

    return render_template('edit_profile.html', user=user)


@app.route('/group_members/<int:group_id>', methods=['GET'])
def group_members(group_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    group = Group.query.get_or_404(group_id)
    user = User.query.filter_by(username=session['username']).first()

    if user not in group.members:
        return "You are not a member of this group", 403

    members = group.members  # Fetch the group members
    return render_template('group_members.html', group=group, members=members)


@app.route('/friend_requests', methods=['GET', 'POST'])
def view_friend_requests():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    if not user:
        return redirect(url_for('login'))

    # Fetch all pending friend requests received by the user
    received_requests = FriendRequest.query.filter_by(receiver_id=user.id, status='pending').all()

    # Fetch all friend requests sent by the user
    sent_requests = FriendRequest.query.filter_by(sender_id=user.id, status='pending').all()

    if request.method == 'POST':
        request_id = request.form.get('request_id')
        action = request.form.get('action')

        friend_request = FriendRequest.query.get(request_id)
        if friend_request and friend_request.receiver_id == user.id:
            if action == 'accept':
                friend_request.status = 'accepted'
                # Add both users as friends
                sender = User.query.get(friend_request.sender_id)
                if sender not in user.friends:
                    user.friends.append(sender)
                if user not in sender.friends:
                    sender.friends.append(user)
                db.session.commit()
            elif action == 'decline':
                friend_request.status = 'declined'
                db.session.commit()

        return redirect(url_for('view_friend_requests'))

    return render_template('friend_requests.html', received_requests=received_requests, sent_requests=sent_requests)



@app.route('/view_friends')
def view_friends():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    friends_list = user.friends.all()  # Fetch all friends

    return render_template('friends_list.html', friends=friends_list)



@app.route('/search_user')
def search_user():
    query = request.args.get('query')
    users = User.query.filter(User.username.ilike(f'%{query}%')).all()
    return jsonify({'users': [{'id': user.id, 'username': user.username} for user in users]})

@app.route('/get_user_profile/<int:user_id>')
def get_user_profile(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({'id': user.id, 'username': user.username, 'email': user.email, 'profile_pic': user.profile_pic or 'default.jpg'})

@app.route('/add_member_to_group', methods=['POST'])
def add_member_to_group():
    data = request.json
    group_id = data.get('group_id')
    user_id = data.get('user_id')
    group = Group.query.get_or_404(group_id)
    user = User.query.get_or_404(user_id)
    if user not in group.members:
        group.members.append(user)
        db.session.commit()
        return '', 200
    return '', 400




@app.route('/respond_friend_request/<int:request_id>/<response>', methods=['POST'])
def respond_friend_request(request_id, response):
    if 'username' not in session:
        return redirect(url_for('login'))

    friend_request = FriendRequest.query.get_or_404(request_id)
    if response == 'accept':
        friend_request.status = 'accepted'
        # Add both users as friends
        sender = User.query.get(friend_request.sender_id)
        receiver = User.query.get(friend_request.receiver_id)
        if sender not in receiver.friends:
            receiver.friends.append(sender)
        if receiver not in sender.friends:
            sender.friends.append(receiver)
    else:
        friend_request.status = 'declined'

    db.session.commit()
    return redirect(url_for('view_friend_requests'))




@app.route('/reels', methods=['GET', 'POST'])
def reels():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    reels = Reel.query.order_by(Reel.id.desc()).all()

    return render_template('reels.html', user=user, reels=reels)


@app.route('/upload_reel', methods=['GET', 'POST'])
def upload_reel():
    if request.method == 'POST':
        reel_file = request.files['reel_file']
        reel_title = request.form['reel_title']

        if reel_file and reel_title:
            filename = secure_filename(reel_file.filename)
            reel_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            # Save reel details in the database
            new_reel = Reel(title=reel_title, filename=filename)
            db.session.add(new_reel)
            db.session.commit()

            flash('Reel uploaded successfully!')
            return redirect(url_for('upload_reel'))

    return render_template('upload_reel.html')

@app.route('/public_feed')
def public_feed():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    videos = Video.query.order_by(Video.id.desc()).all()  # Fetch all videos in descending order

    # Fetch received friend requests
    received_requests = FriendRequest.query.filter_by(receiver_id=user.id, status='pending').all()

    # Define user_profile_pic
    user_profile_pic = user.profile_pic if user.profile_pic else 'default.jpg'

    # Pass user_profile_pic to the template
    return render_template('public_feed.html', user=user, user_profile_pic=user_profile_pic, videos=videos, received_requests=received_requests)


@app.route('/upload_video', methods=['GET', 'POST'])
def upload_video():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']
        tags = request.form['tags']
        privacy = request.form['privacy']
        video_file = request.files['video_file']
        thumbnail = request.files.get('thumbnail')

        # Ensure the directory exists
        video_dir = os.path.join(app.config['UPLOAD_FOLDER'])
        if not os.path.exists(video_dir):
            os.makedirs(video_dir)

        if video_file:
            # Secure the filename and save the video file
            filename = secure_filename(video_file.filename)
            video_path = os.path.join(video_dir, filename)
            video_file.save(video_path)

            # Handle the thumbnail
            if thumbnail:
                thumbnail_filename = secure_filename(thumbnail.filename)
                thumbnail_path = os.path.join(app.config['UPLOAD_FOLDER'], thumbnail_filename)
                thumbnail.save(thumbnail_path)
            else:
                # Generate thumbnail from video if none provided (using a placeholder for now)
                thumbnail_filename = 'default_thumbnail.jpg'

            uploader = User.query.filter_by(username=session['username']).first()
            new_video = Video(
                title=title, 
                description=description, 
                filename=filename, 
                category=category, 
                uploader_id=uploader.id,
                tags=tags,
                thumbnail=thumbnail_filename,
                privacy=privacy
            )
            db.session.add(new_video)
            db.session.commit()
            return redirect(url_for('view_video', video_id=new_video.id))
    
    return render_template('upload_video.html')


@app.route('/friend_list')
def friend_list():
    if 'username' not in session:
        return redirect(url_for('login'))

    # Fetch the current logged-in user
    user = User.query.filter_by(username=session['username']).first()
    
    if not user:
        return redirect(url_for('login'))

    friends = user.friends.all()  # Fetch all friends of the current user

    # Pass the user object along with the list of friends to the template
    return render_template('friend_list.html', user=user, friends=friends)



@app.route('/tweet', methods=['GET', 'POST'])
def tweet():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        content = request.form['content']
        # Logic to save tweet content to the database
        # Example: new_tweet = Tweet(content=content, user_id=user.id)
        # db.session.add(new_tweet)
        # db.session.commit()
        return redirect(url_for('dashboard'))
    
    return render_template('tweet.html')

@app.route('/upload_photo', methods=['GET', 'POST'])
def upload_photo():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        photo_file = request.files['photo_file']
        if photo_file:
            photo_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'photos')
            if not os.path.exists(photo_dir):
                os.makedirs(photo_dir)
            
            filename = secure_filename(photo_file.filename)
            photo_path = os.path.join(photo_dir, filename)
            photo_file.save(photo_path)
            # Logic to save photo details to the database
            return redirect(url_for('dashboard'))
    
    return render_template('upload_photo.html')


@app.route('/react_video/<int:video_id>', methods=['POST'])
def react_video(video_id):
    if 'username' not in session:
        return jsonify({'status': 'unauthorized'}), 401

    user = User.query.filter_by(username=session['username']).first()
    reaction_type = request.json.get('reaction_type')
    existing_reaction = Reaction.query.filter_by(video_id=video_id, user_id=user.id).first()

    if existing_reaction:
        existing_reaction.reaction_type = reaction_type
    else:
        new_reaction = Reaction(video_id=video_id, user_id=user.id, reaction_type=reaction_type)
        db.session.add(new_reaction)

    db.session.commit()

    # Get the updated number of reactions for this video
    reaction_count = Reaction.query.filter_by(video_id=video_id).count()

    return jsonify({'status': 'success', 'reaction_count': reaction_count}), 200


@app.route('/share_video/<int:video_id>', methods=['POST'])
def share_video(video_id):
    if 'username' not in session:
        return jsonify({'status': 'unauthorized'}), 401

    user = User.query.filter_by(username=session['username']).first()
    video = Video.query.get(video_id)

    # Create a new video entry as a "shared" post
    shared_video = Video(
        title=f"Shared: {video.title}",
        description=video.description,
        filename=video.filename,  # Use the same video file
        uploader_id=user.id,
        category=video.category,
        tags=video.tags,
        thumbnail=video.thumbnail,
        privacy=video.privacy
    )
    db.session.add(shared_video)
    db.session.commit()

    return jsonify({'status': 'success'}), 200


@app.route('/comment_video/<int:video_id>', methods=['POST'])
def comment_video(video_id):
    if 'username' not in session:
        return 'Unauthorized', 401

    user = User.query.filter_by(username=session['username']).first()
    comment_content = request.json.get('comment')
    new_comment = Comment(video_id=video_id, user_id=user.id, content=comment_content)
    db.session.add(new_comment)
    db.session.commit()

    # Emit the update to all connected clients
    comment_count = Comment.query.filter_by(video_id=video_id).count()
    socketio.emit('update_comments', {'video_id': video_id, 'comment_count': comment_count})

    return jsonify({'status': 'success'}), 200


@app.route('/view_reels')
def view_reels():
    reels = Reel.query.all()  # Fetch all uploaded reels from the database
    return render_template('view_reels.html', reels=reels)

@app.route('/video/<int:video_id>', methods=['GET', 'POST'])
def view_video(video_id):
    video = Video.query.get_or_404(video_id)
    uploader = User.query.get(video.uploader_id)
    comments = Comment.query.filter_by(video_id=video.id).all()
    
    if request.method == 'POST':
        if 'reaction' in request.form:
            reaction_type = request.form['reaction']
            user = User.query.filter_by(username=session['username']).first()
            new_reaction = Reaction(video_id=video.id, user_id=user.id, reaction_type=reaction_type)
            db.session.add(new_reaction)
            db.session.commit()
        elif 'comment' in request.form:
            comment_content = request.form['comment']
            user = User.query.filter_by(username=session['username']).first()
            new_comment = Comment(video_id=video.id, user_id=user.id, content=comment_content)
            db.session.add(new_comment)
            db.session.commit()
    
    return render_template('view_video.html', video=video, uploader=uploader, comments=comments)



@app.route('/notifications')
def notifications():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()

    # Fetch notifications for the user
    user_notifications = Notification.query.filter_by(user_id=user.id).all()

    return render_template('notifications.html', notifications=user_notifications)


@app.route('/logout')
def logout():
    # Clear the session to log out the user
    session.clear()
    return redirect(url_for('login'))


@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        search_query = request.form['search_query']
        try:
            results = User.query.filter(User.username.contains(search_query)).all()
        except Exception as e:
            print(f"Error during user search: {e}")
            return "An error occurred during search", 500
        
        return render_template('search.html', results=results)
    
    return render_template('search.html')



@app.route('/counsel_request/<int:receiver_id>', methods=['POST'])
def counsel_request(receiver_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    sender = User.query.filter_by(username=session['username']).first()
    receiver = User.query.get(receiver_id)

    if receiver and receiver != sender:
        # Logic to handle counsel request
        # You can implement the logic to store the request or notify the user here
        return f'Counsel request sent to {receiver.username}!', 200
    return redirect(url_for('search'))



@app.route('/profile/<int:user_id>', methods=['GET', 'POST'])
def view_profile(user_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get_or_404(user_id)
    current_user = User.query.filter_by(username=session['username']).first()
    
    # Check if the profile being viewed is the current logged-in user's profile
    is_current_user = (current_user.id == user.id)
    
    # Handle form submission for actions like adding a friend or giving a star
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_friend':
            if user not in current_user.friends:
                current_user.friends.append(user)
                db.session.commit()
                session['friends'] = [friend.username for friend in current_user.friends]
        elif action == 'give_star':
            user.stars_received += 1
            db.session.commit()
    
    # Check if the profile user is a friend of the current user
    is_friend = user in current_user.friends

    return render_template('profile.html', user=user, is_current_user=is_current_user, is_friend=is_friend)


@app.route('/group_chat/<int:group_id>', methods=['GET', 'POST'])
def group_chat(group_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    group = Group.query.get_or_404(group_id)
    user = User.query.filter_by(username=session['username']).first()

    if user not in group.members:
        return "You are not a member of this group", 403

    if request.method == 'POST':
        message_content = request.form.get('message')
        if message_content:
            new_message = Message(content=message_content, user_id=user.id, group_id=group.id)
            db.session.add(new_message)
            db.session.commit()

    messages = Message.query.filter_by(group_id=group.id).order_by(Message.timestamp).all()

    return render_template('group_chat.html', group=group, messages=messages)

# Add socketio events for group chat
@socketio.on('send_group_message')
def handle_group_message(data):
    group_id = data['group_id']
    message = data['message']
    username = session['username']

    # Save message in the database
    group = Group.query.get(group_id)
    if group:
        user = User.query.filter_by(username=username).first()
        new_message = Message(content=message, user_id=user.id, group_id=group_id)
        db.session.add(new_message)
        db.session.commit()

    # Emit the message to the group
    socketio.emit('new_group_message', {
        'username': username,
        'message': message,
        'group_id': group_id
    }, room=f'group_{group_id}')

@app.route('/delete_video/<int:video_id>', methods=['POST'])
def delete_video(video_id):
    if 'username' not in session:
        return 'Unauthorized', 401
    
    user = User.query.filter_by(username=session['username']).first()
    video = Video.query.get_or_404(video_id)

    if video.uploader_id != user.id:
        return 'Unauthorized to delete this video', 403

    # Delete the video from the database
    db.session.delete(video)
    db.session.commit()

    return 'Video deleted successfully', 200


@app.route('/chat')
def chat():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    friends = user.friends  # Fetch user's friends
    groups = user.groups    # Fetch user's groups
    return render_template('chat.html', user=user, friends=friends, groups=groups)

@app.route('/chat/<int:user_id>', methods=['GET', 'POST'])
def private_chat(user_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    current_user = User.query.filter_by(username=session['username']).first()
    chat_user = User.query.get_or_404(user_id)

    room = f'private_{min(current_user.id, chat_user.id)}_{max(current_user.id, chat_user.id)}'

    # Check if a message is sent
    if request.method == 'POST':
        message_content = request.form['message']
        if message_content:
            # Save the new message to the database
            new_message = PrivateMessage(
                content=message_content,
                sender_id=current_user.id,
                receiver_id=chat_user.id
            )
            db.session.add(new_message)
            db.session.commit()

            # Send the message to the recipient in real-time using SocketIO
            socketio.emit('receive_private_message', {
                'sender': current_user.username,
                'message': message_content,
                'timestamp': new_message.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'room': room
            }, room=room)

    # Retrieve all private messages between the two users
    messages = PrivateMessage.query.filter(
        ((PrivateMessage.sender_id == current_user.id) & (PrivateMessage.receiver_id == chat_user.id)) |
        ((PrivateMessage.sender_id == chat_user.id) & (PrivateMessage.receiver_id == current_user.id))
    ).order_by(PrivateMessage.timestamp).all()

    return render_template('private_chat.html', current_user=current_user, chat_user=chat_user, messages=messages, room=room)




@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    # Fetch the latest user data from the database
    user = User.query.filter_by(username=session['username']).first() 

    # Ensure session['friends'] is initialized
    if 'friends' not in session:
        session['friends'] = [friend.username for friend in user.friends]

    # Fetch user's friends
    friends = User.query.filter(User.username.in_(session['friends'])).all()  
    # Fetch all videos for simplicity
    videos = Video.query.order_by(Video.id.desc()).all()  

    # Handle None values to prevent TypeError
    user_profile_pic = user.profile_pic if user.profile_pic else 'default.jpg'
    user_gpa_class_9 = user.gpa_class_9 if user.gpa_class_9 else 'Not provided'
    user_gpa_class_10 = user.gpa_class_10 if user.gpa_class_10 else 'Not provided'
    user_gpa_class_11 = user.gpa_class_11 if user.gpa_class_11 else 'Not provided'
    user_gpa_class_12 = user.gpa_class_12 if user.gpa_class_12 else 'Not provided'
    user_sat_score = user.sat_score if user.sat_score else 'Not provided'
    user_gpa = user.gpa if user.gpa else 'Not provided'
    user_eca = user.eca if user.eca else 'Not provided'
    user_essay = user.essay if user.essay else 'Not provided'
    universities_to_apply = user.universities_to_apply if user.universities_to_apply else 'Not provided'
    universities_applied = user.universities_applied if user.universities_applied else 'Not provided'
    universities_studying = user.universities_studying if user.universities_studying else 'Not provided'

    # Render the dashboard template with all user data
    return render_template('dashboard.html', user=user, friends=friends, videos=videos, 
                           user_profile_pic=user_profile_pic, user_gpa_class_9=user_gpa_class_9,
                           user_gpa_class_10=user_gpa_class_10, user_gpa_class_11=user_gpa_class_11,
                           user_gpa_class_12=user_gpa_class_12, user_sat_score=user_sat_score,
                           user_gpa=user_gpa, user_eca=user_eca, user_essay=user_essay,
                           universities_to_apply=universities_to_apply, universities_applied=universities_applied,
                           universities_studying=universities_studying)


@app.route('/add_friend/<int:friend_id>', methods=['POST'])
def add_friend(friend_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    friend = User.query.get(friend_id)

    if friend and friend not in user.friends:
        user.friends.append(friend)
        db.session.commit()

    return redirect(url_for('view_profile', user_id=friend_id))



@socketio.on('join')
def on_join(room):
    username = session['username']
    join_room(room)
    if room not in users_in_rooms:
        users_in_rooms[room] = []
    users_in_rooms[room].append(username)

    # Remove the send message here to stop broadcasting the system message
    # socketio.emit('newMessage', {'username': 'System', 'text': f'{username} has joined the room.'}, room=room)

    # Emit updated user list without sending a message to the chat
    socketio.emit('updateUsersList', users_in_rooms[room], room=room)


@socketio.on('leave')
def on_leave(room):
    username = session['username']
    leave_room(room)
    users_in_rooms[room].remove(username)

    # Remove the send message here to stop broadcasting the system message
    # socketio.emit('newMessage', {'username': 'System', 'text': f'{username} has left the room.'}, room=room)

    # Emit updated user list without sending a message to the chat
    socketio.emit('updateUsersList', users_in_rooms[room], room=room)



@socketio.on('send_private_message')
def handle_private_message(data):
    room = data['room']
    message_content = data['message']
    sender = session['username']

    # Get the current user (sender)
    current_user = User.query.filter_by(username=sender).first()

    # Find the chat recipient based on the room identifier
    # You can extract recipient_id from the room name or pass it explicitly
    room_users = room.split('_')[1:]  # Get user ids from room name
    recipient_id = room_users[1] if str(current_user.id) == room_users[0] else room_users[0]
    recipient = User.query.get(recipient_id)

    # Save the new message to the database
    new_message = PrivateMessage(
        content=message_content,
        sender_id=current_user.id,
        receiver_id=recipient.id
    )
    db.session.add(new_message)
    db.session.commit()

    # Send the message to both users in real-time
    socketio.emit('receive_private_message', {
        'sender': current_user.username,
        'message': message_content,
        'timestamp': new_message.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'room': room
    }, room=room)




@socketio.on('sendMessage')
def handle_message(data):
    room = data['room']
    username = session['username']
    message = data['text']
    timestamp = datetime.now().strftime('%H:%M:%S')
    send({'username': username, 'text': message, 'time': timestamp}, room=room)


# Define your routes here...
# [Your route code here...]

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)







