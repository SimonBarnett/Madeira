import jwt
import datetime
from flask import current_app, request, jsonify, url_for
from functools import wraps
import bcrypt
from .users import load_users_settings, save_users_settings, generate_code

def login_required(required_permissions, require_all=True):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            if not token:
                return jsonify({"status": "error", "message": "Token required"}), 401
            try:
                payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
                if datetime.datetime.utcnow().timestamp() > payload["exp"]:
                    return jsonify({"status": "error", "message": "Token expired"}), 401
                request.user_id = payload["userId"]
                request.permissions = payload.get("permissions", [])
                effective_perms = []
                for perm in required_permissions:
                    if perm == "allauth":
                        effective_perms.extend(["admin", "merchant", "community", "wixpro"])
                    elif perm == "self":
                        user_id = next((v for v in kwargs.values() if isinstance(v, str)), None)
                        if user_id and request.user_id != user_id:
                            effective_perms.append(None)
                        else:
                            effective_perms.append("self")
                    else:
                        effective_perms.append(perm)
                if require_all:
                    if not all(p in request.permissions for p in effective_perms if p and p != "self"):
                        return jsonify({"status": "error", "message": f"Insufficient permissions: {effective_perms}"}), 403
                else:
                    if not any(p in request.permissions for p in effective_perms if p and p != "self"):
                        return jsonify({"status": "error", "message": f"Insufficient permissions: {effective_perms}"}), 403
                return f(*args, **kwargs)
            except jwt.InvalidTokenError:
                return jsonify({"status": "error", "message": "Invalid token"}), 401
            except Exception as e:
                return jsonify({"status": "error", "message": f"Token error: {str(e)}"}), 500
        return decorated_function
    return decorator

def login_user():
    data = request.get_json()
    if not data or 'email' not in data or 'password' not in data:
        return jsonify({"status": "error", "message": "Email and password required"}), 400
    email = data["email"].strip().lower()
    password = data["password"].strip()
    users_settings = load_users_settings()
    user_id = None
    for uid, settings in users_settings.items():
        if settings.get("email_address", "").lower() == email and bcrypt.checkpw(password.encode('utf-8'), settings["password"].encode('utf-8')):
            user_id = uid
            break
    if not user_id:
        return jsonify({"status": "error", "message": "Invalid credentials"}), 401
    permissions = users_settings[user_id].get("permissions", [])
    token = jwt.encode(
        {"userId": user_id, "permissions": permissions, "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)},
        current_app.config['JWT_SECRET_KEY'],
        algorithm="HS256"
    )
    
    # Determine redirect URL based on permissions
    redirect_url = None
    if "admin" in permissions:
        redirect_url = url_for('admin')  # Assuming an admin route exists
    elif "merchant" in permissions:
        redirect_url = url_for('merchant')  # Assuming a merchant route exists
    elif "community" in permissions:
        redirect_url = url_for('community')  # Assuming a community route exists
    elif "wixpro" in permissions:
        redirect_url = url_for('wixpro')  # Assuming a wixpro route exists
    else:
        redirect_url = url_for('home')  # Default fallback

    response_data = {
        "status": "success",
        "token": token,
        "userId": user_id,
        "redirect_url": redirect_url  # Add redirect URL to response
    }
    return jsonify(response_data), 200

def signup_user():
    data = request.get_json()
    # Base required fields
    required_fields = ['signup_type', 'contact_name', 'signup_email', 'signup_password']
    if not all(k in data for k in required_fields):
        return jsonify({"status": "error", "message": "Signup type, contact name, email, and password are required"}), 400

    # Phone number is required for community and merchant, optional for wixpro
    signup_type = data['signup_type']
    signup_phone = data.get('signup_phone')
    if signup_type in ['community', 'seller'] and (signup_phone is None or signup_phone == ''):
        return jsonify({"status": "error", "message": "Phone number is required for Community Group and Merchant signups"}), 400

    # Validate phone number format if provided
    if signup_phone:
        import re
        if not re.match(r'^\d{10}$', signup_phone):
            return jsonify({"status": "error", "message": "Phone number must be a 10-digit number with no spaces or special characters"}), 400

    users_settings = load_users_settings()
    if any(u['email_address'] == data['signup_email'] for u in users_settings.values()):
        return jsonify({"status": "error", "message": "Email exists"}), 400

    USERid = generate_code()
    hashed_password = bcrypt.hashpw(data['signup_password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    users_settings[USERid] = {
        "email_address": data['signup_email'],
        "password": hashed_password,
        "contact_name": data['contact_name'],
        "phone_number": signup_phone,  # Store the phone number
        "permissions": [data['signup_type']]
    }
    save_users_settings(users_settings)
    return jsonify({"status": "success", "message": "Signup successful"}), 201

def generate_token(user_id, permissions):
    """Generate a JWT token with user_id and permissions."""
    payload = {
        "userId": user_id,  # Match login_user key
        "permissions": permissions,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)  # 24-hour expiry
    }
    return jwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')