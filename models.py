from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.mutable import MutableList

from flask_security import RoleMixin, UserMixin, AsaList, SQLAlchemyUserDatastore


db = SQLAlchemy()

# Association table for many-to-many relationship between users and roles
class RolesUsers(db.Model):
    __tablename__ = 'roles_users'
    id = db.Column(db.Integer(), primary_key=True)
    user_id = db.Column('user_id', db.Integer(), db.ForeignKey('user.id')) # Foreign key reference to User
    role_id = db.Column('role_id', db.Integer(), db.ForeignKey('role.id')) # Foreign key reference to Role

# Role model defining roles within the application
class Role(db.Model, RoleMixin):
    __tablename__ = 'role'
    id = db.Column(db.Integer(), primary_key=True) 
    name = db.Column(db.String(80), unique=True)
    # permissions = db.Column(MutableList.as_mutable(AsaList()), nullable=True)
# # User model extending Flask-Security's UserMixin for authentication and RBAC
class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True) 

    email = db.Column(db.String(255), unique=True, nullable=False) 
    name = db.Column(db.String(255), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    pincode = db.Column(db.String(255), nullable=False)
    phone_number = db.Column(db.String(255), nullable=False)

    # Professional specific fields
    service_type = db.Column(db.String(255), nullable=True)
    experience = db.Column(db.Integer, nullable=True) # Experience in years
    document_path = db.Column(db.String(255), nullable=True)
    active = db.Column(db.Boolean(), nullable=True) # Active status of professional
    approved = db.Column(db.Boolean(), nullable=True) # Approval status of professional

    last_login_at = db.Column(db.DateTime())
    current_login_at = db.Column(db.DateTime())
    last_login_ip = db.Column(db.String(100))
    current_login_ip = db.Column(db.String(100))
    login_count = db.Column(db.Integer)

    fs_uniquifier = db.Column(db.String(64), unique=True, nullable=False) #

    # confirmed_at = db.Column(db.DateTime())

    # Establishing a many-to-many relationship between users and roles

    roles = db.relationship('Role', secondary='roles_users',
                         backref=db.backref('users', lazy='dynamic'))
    
    def serialize(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'address': self.address,
            'pincode': self.pincode,
            'phone_number': self.phone_number,
            'service_type': self.service_type,
            'experience': self.experience,
            'document_path': self.document_path,
            'active': self.active,
            'approved': self.approved,
            'roles': [role.name for role in self.roles],
            'average_rating': self.get_average_rating()
        }
    
    def get_average_rating(self):
        reviews = Review.query.filter_by(professional_id=self.id).all()
        if not reviews:
            return 0.0
        return round(sum([review.rating for review in reviews]) / len(reviews), 2)
    
    
    
# Initialize Flask-Security's SQLAlchemy datastore for managing users and roles
user_datastore = SQLAlchemyUserDatastore(db, User, Role)

class Category(db.Model):
    __tablename__ = 'category'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255), nullable=True)

    services = db.relationship('Service', backref='category', lazy=True, cascade='all, delete-orphan')

    def serialize(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'services': [service.serialize() for service in self.services]
        }
    
    def get_all_categories():
        return Category.query.all()
    
    def get_category_by_id(id):
        return Category.query.get(id)
    
    def admin_delete_category(id):
        category = Category.query.get(id)
        if not category:
            return "Category not found", False
        db.session.delete(category)
        db.session.commit()
        return "Category deleted successfully", True


class Service(db.Model):
    __tablename__ = 'service'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    price = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)

    

    def serialize(self):
        category = Category.query.get(self.category_id)
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'price': self.price,
            'category_id': self.category_id,
            'category_name': category.name if category else 'Uncategorized'
        }
    
    def get_all_services():
        return Service.query.all()
    
    def get_service_by_id(id):
        return Service.query.get(id)
    
    def admin_delete_service(id):
        service = Service.query.get(id)
        if not service:
            return "Service not found", False
        db.session.delete(service)
        db.session.commit()
        return "Service deleted successfully", True
    
class ServiceRequest(db.Model):
    __tablename__ = 'service_request'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # ID of the customer who made the request
    professional_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # ID of the professional assigned to the request
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)  # ID of the requested service
    request_date = db.Column(db.DateTime, default=db.func.current_timestamp())  # Date of request creation
    status = db.Column(db.String(50), default='Pending')  # Status: Pending, Accepted, Rejected, Completed, Cancelled
    customer_review = db.Column(db.String(255), nullable=True)  # Optional review by customer after service completion

    customer = db.relationship('User', foreign_keys=[customer_id], backref='customer_requests')
    professional = db.relationship('User', foreign_keys=[professional_id], backref='professional_requests')
    service = db.relationship('Service', backref='service_requests')

    def serialize(self):
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'professional_id': self.professional_id,
            'service_id': self.service_id,
            'request_date': self.request_date,
            'status': self.status,
            'customer_review': self.customer_review,
        }
    
    # Functions to handle request status changes
    def accept_request(self):
        self.status = 'Accepted'
        db.session.commit()

    def reject_request(self):
        self.status = 'Rejected'
        db.session.commit()

    def complete_request(self):
        self.status = 'Completed'
        db.session.commit()

class Review(db.Model):
    __tablename__ = 'review'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # ID of the customer who made the review
    professional_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # ID of the professional who received the review
    rating = db.Column(db.Integer, nullable=False)  # Rating given by the customer
    review_text = db.Column(db.String(255), nullable=False)  # Review text given by the customer

    customer = db.relationship('User', foreign_keys=[customer_id], backref='customer_reviews')
    professional = db.relationship('User', foreign_keys=[professional_id], backref='professional_reviews')

    def serialize(self):
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'professional_id': self.professional_id,
            'rating': self.rating,
            'review_text': self.review_text,
        }
    
    def get_all_reviews():
        return Review.query.all()
    
    def get_review_by_id(id):
        return Review.query.get(id)
    
    def admin_delete_review(id):
        review = Review.query.get(id)
        if not review:
            return "Review not found", False
        db.session.delete(review)
        db.session.commit()
        return "Review deleted successfully", True

    