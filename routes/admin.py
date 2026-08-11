from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from models.auth_db import (
    get_all_users, get_user_by_id, create_user, update_user, delete_user, count_users
)

admin = Blueprint("admin", __name__)


def admin_required(f):
    """Decorator to restrict access to admin users only."""
    from functools import wraps

    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != "admin":
            flash("Access denied. Admin privileges required.", "danger")
            return redirect(url_for("bookmarks.dashboard"))
        return f(*args, **kwargs)
    return decorated_function


@admin.route("/admin/users")
@admin_required
def list_users():
    """List all users - admin only."""
    users = get_all_users()
    return render_template("admin/users.html", users=users)


@admin.route("/admin/users/create", methods=["GET", "POST"])
@admin_required
def create_user_view():
    """Create a new user - admin only."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validation
        errors = []
        if not username:
            errors.append("Username is required.")
        if len(username) < 3:
            errors.append("Username must be at least 3 characters long.")
        if " " in username:
            errors.append("Username cannot contain spaces.")
        if not password:
            errors.append("Password is required.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if password != confirm_password:
            errors.append("Passwords do not match.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("admin/create_user.html", username=username)

        # Create user (always as 'user' role - admin cannot promote)
        if create_user(username, password, role="user"):
            flash(f"User '{username}' created successfully.", "success")
            return redirect(url_for("admin.list_users"))
        else:
            flash("Username already taken.", "danger")
            return render_template("admin/create_user.html", username=username)

    return render_template("admin/create_user.html")


@admin.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_user(user_id):
    """Edit a user - admin only."""
    user = get_user_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.list_users"))

    # Prevent editing the main admin account
    if user["username"] == "admin":
        flash("Cannot edit the main admin account.", "warning")
        return redirect(url_for("admin.list_users"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validation
        errors = []
        if not username:
            errors.append("Username is required.")
        if len(username) < 3:
            errors.append("Username must be at least 3 characters long.")
        if " " in username:
            errors.append("Username cannot contain spaces.")
        if password and len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if password and password != confirm_password:
            errors.append("Passwords do not match.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("admin/edit_user.html", user=user)

        # Update user (role is not changeable - always 'user')
        update_kwargs = {"username": username}
        if password:
            update_kwargs["password"] = password

        if update_user(user_id, **update_kwargs):
            flash(f"User '{username}' updated successfully.", "success")
            return redirect(url_for("admin.list_users"))
        else:
            flash("Username already taken.", "danger")
            return render_template("admin/edit_user.html", user=user)

    return render_template("admin/edit_user.html", user=user)


@admin.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user_view(user_id):
    """Delete a user - admin only."""
    user = get_user_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.list_users"))

    # Prevent deleting the main admin account
    if user["username"] == "admin":
        flash("Cannot delete the main admin account.", "warning")
        return redirect(url_for("admin.list_users"))

    # Prevent self-deletion
    if user_id == current_user.id:
        flash("Cannot delete your own account from here.", "warning")
        return redirect(url_for("admin.list_users"))

    username = user["username"]
    delete_user(user_id)
    flash(f"User '{username}' deleted successfully.", "success")
    return redirect(url_for("admin.list_users"))
