from flask import Flask, request, jsonify, send_from_directory, send_file
import os
from caching import cache
from flask_security import Security, UserMixin, RoleMixin, login_required, current_user, logout_user, roles_accepted, roles_required, auth_token_required
from werkzeug.utils import secure_filename
from models import db, User, Role, RolesUsers, user_datastore, Category, Service, ServiceRequest, Review

def create_celery(init_app):
    from celery import Celery
    init_celery = Celery(init_app.import_name)
    import celery_config
    init_celery.config_from_object(celery_config)
    return init_celery

def create_app():
    init_app = Flask(__name__)

    from config import localdev
    init_app.config.from_object(localdev)

    # db = SQLAlchemy(app)
    db.init_app(init_app)
    security=Security(init_app, user_datastore)

    from flask_restful import Api
    init_api = Api(init_app)

    from mailer import mailer
    mailer.init_app(init_app)

    from caching import cache
    cache.init_app(init_app)


    # return init_app, init_api
    return init_app, init_api

app, api = create_app()

from celery import Celery
app_celery = Celery(app.import_name)
import celery_config
app_celery.config_from_object('celery_config')
import celery_tasks

from celery.schedules import crontab

app_celery.conf.beat_schedule = {
      'schedule1': {
          'task': 'celery_tasks.hello_world',
          'schedule': crontab(minute=21 , hour=00)   
      },
      'schedule_remind_professionals_to_complete_requests': {
          'task': 'celery_tasks.remind_professionals_to_complete_requests',
          'schedule': crontab(minute='*') # Every minute
    },
    'schedule_send_monthly_activity_report': {
        'task': 'celery_tasks.send_monthly_activity_report',
        'schedule': crontab(minute=13, hour=13, day_of_month='1'),  # Runs at midnight on the 1st of each month
    }
}

from flask_cors import CORS
CORS(app)

# Ensuring Upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Create the database tables
with app.app_context():
    db.create_all()
    user_datastore.find_or_create_role(name='admin')
    user_datastore.find_or_create_role(name='professional')
    user_datastore.find_or_create_role(name='customer')
    db.session.commit()

    if not user_datastore.find_user(email="a@abc.com"):
        admin_user = user_datastore.create_user(email="a@abc.com", password="123", name="a", address="a", pincode="a", phone_number="a")
        role = user_datastore.find_role('admin')
        user_datastore.add_role_to_user(admin_user, role)
        db.session.commit()

@app.route('/remind_professionals_to_complete_requests', methods=['GET'])
def remind_professionals_to_complete_requests():
    result = celery_tasks.remind_professionals_to_complete_requests.delay()
    return jsonify({'message': 'Task scheduled successfully', 'task_id': result.id, 'result': result.result}), 200

@app.route('/send_monthly_activity_report', methods=['GET'])
def send_monthly_activity_report():
    result = celery_tasks.send_monthly_activity_report.delay()
    return jsonify({'message': 'Task scheduled successfully', 'task_id': result.id, 'result': result.result}), 200

@app.route('/trigger-csv-export', methods=['POST'])
def trigger_csv_export():
    job = celery_tasks.export_closed_requests_to_csv.apply_async()
    return jsonify({"task_id": job.id, "message": "Export started. You'll be notified once it's complete."}), 202

@app.route('/check-export-status/<task_id>', methods=['GET'])
def check_export_status(task_id):
    job = celery_tasks.export_closed_requests_to_csv.AsyncResult(task_id)
    if job.state == 'SUCCESS':
        file_path = job.result
        filename = os.path.basename(file_path)
        return send_file(file_path, as_attachment=True, download_name=filename)


    elif job.state == 'PENDING':
        return jsonify({"status": "Pending"})
    else:
        return jsonify({"status": "Error", "error_message": str(job.info)})

# Route to retrieve professionals - requires admin role
@app.route('/professionals', methods=['GET'])
@roles_required('admin')
@auth_token_required
def get_professionals():
    professionals = User.query.filter(User.roles.any(name='professional')).all()
    return jsonify([p.serialize() for p in professionals])

# Serve the document file
@app.route('/static/uploads/<filename>')
def serve_file(filename):
    return send_from_directory(os.path.join(app.root_path, 'static/uploads'), filename)

# Route to retrieve customers - requires admin role
@app.route('/api/customers', methods=['GET'])
@roles_required('admin')
@auth_token_required
def get_customers():
    customers = User.query.filter(User.roles.any(name='customer')).all()
    return jsonify([c.serialize() for c in customers])

# Route to approve a professional - requires admin role
@app.route('/approve/professional', methods=['POST'])
@roles_required('admin')
@auth_token_required
def approve_professional():
    data = request.get_json()
    professional_id = data.get('professional_id')
    professional = User.query.get(professional_id)
    if professional:
        professional.approved = True  # Modify `approved` status for approval
        db.session.commit()
        return jsonify({"message": "Professional approved"}), 200
    return jsonify({"message": "Professional not found"}), 404

# Route to reject a professional - requires admin role
@app.route('/reject/professional', methods=['POST'])
@roles_required('admin')
@auth_token_required
def reject_professional():
    data = request.get_json()
    professional_id = data.get('professional_id')
    professional = User.query.get(professional_id)
    if professional:
        professional.approved = False  # Modify `approved` status for rejection
        db.session.commit()
        return jsonify({"message": "Professional rejected"}), 200
    return jsonify({"message": "Professional not found"}), 404

# Route to block a professional - requires admin role
@app.route('/block', methods=['POST'])
@roles_required('admin')
@auth_token_required
def block_professional():
    data = request.get_json()
    professional_id = data.get('user_id')
    professional = User.query.get(professional_id)
    if professional:
        professional.active = False  # Modify `active` status for blocking
        db.session.commit()
        return jsonify({"message": "User blocked"}), 200
    return jsonify({"message": "User not found"}), 404

# Route to unblock a professional - requires admin role
@app.route('/unblock', methods=['POST'])
@roles_required('admin')
@auth_token_required
def unblock_professional():
    data = request.get_json()
    professional_id = data.get('user_id')
    professional = User.query.get(professional_id)
    if professional:
        professional.active = True  # Modify `active` status for unblocking
        db.session.commit()
        return jsonify({"message": "User unblocked"}), 200
    return jsonify({"message": "User not found"}), 404

# Routes for managing services - requires admin role
@app.route('/services', methods=['GET', 'POST'])
@roles_required('admin')
@auth_token_required
def manage_services():
    if request.method == 'GET':
        services = Service.query.all()  # Fetch all services
        return jsonify([s.serialize() for s in services])  # Serialize services
    elif request.method == 'POST':
        categories = Category.query.all()
        data = request.get_json()
        new_service = Service(
            name=data['name'],
            description=data['description'],
            price=data['price'],
            # category_name=data['category_id'],  # Get the category name
            # I have category name in the request, so I will get the category id
            category_id=[category.id for category in categories if category.name == data['category_id']][0]
        )
        db.session.add(new_service)
        db.session.commit()
        return jsonify({"message": "Service added successfully"}), 201

# Route to delete a service - requires admin role
@app.route('/services/<int:service_id>', methods=['DELETE'])
@roles_required('admin')
@auth_token_required
def delete_service(service_id):
    service = Service.query.get(service_id)

    if not service:
        return jsonify({"message": "Service not found"}), 404
    
    #Delete the service requests for the service before deleting the service
    service_requests = ServiceRequest.query.filter_by(service_id=service_id).all()
    for service_request in service_requests:
        db.session.delete(service_request)

    if service:
        db.session.delete(service)
        db.session.commit()
        return jsonify({"message": "Service deleted successfully"}), 200
    return jsonify({"message": "Service not found"}), 404

# Route to update a service - requires admin role
@app.route('/services/<int:service_id>', methods=['PUT'])
@roles_required('admin')
@auth_token_required
def update_service(service_id):
    service = Service.query.get(service_id)
    if not service:
        return jsonify({"message": "Service not found"}), 404
    data = request.get_json()
    service.name = data.get('name', service.name)
    service.description = data.get('description', service.description)
    service.price = data.get('price', service.price)
    # service.category_id = data.get

    if 'category_id' in data:
        category = Category.query.filter_by(name=data['category_id']).first()
        if category:
            service.category_id = category.id
        else:
            return jsonify({"message": "Category not found"}), 400
        
    db.session.commit()
    return jsonify({"message": "Service updated successfully"}), 200

@app.route('/signup/customer', methods=['POST'])
def signup_customer():
    data = request.get_json()
    email = data.get('email')
    name = data.get('name')
    password = data.get('password')
    address = data.get('address')
    pincode = data.get('pincode')
    phone_number = data.get('phone_number')

    if not email:
        return jsonify({'message': 'Email is required'}), 400
    if not name:
        return jsonify({'message': 'Name is required'}), 400
    if not password:
        return jsonify({'message': 'Password is required'}), 400
    if not address:
        return jsonify({'message': 'Address is required'}), 400
    if not pincode:
        return jsonify({'message': 'Pincode is required'}), 400
    if not phone_number:
        return jsonify({'message': 'Phone number is required'}), 400
    
    if user_datastore.find_user(email=email):
        return jsonify({'message': 'User already exists'}), 400
    
    user = user_datastore.create_user(email=email, name=name, password=password, address=address, pincode=pincode, phone_number=phone_number)
    user_datastore.add_role_to_user(user, 'customer')
    db.session.commit()
    return jsonify({'message': 'Customer created successfully'})
from flask import request, jsonify
from werkzeug.utils import secure_filename
import os

@app.route('/signup/professional', methods=['POST'])
def signup_professional():
    # Retrieve form data
    email = request.form.get('email')
    name = request.form.get('name')
    password = request.form.get('password')
    address = request.form.get('address')
    pincode = request.form.get('pincode')
    phone_number = request.form.get('phone_number')
    service_type = request.form.get('service_type')
    experience = request.form.get('experience')

    # Handle file upload
    document = request.files.get('document')  # This retrieves the uploaded file

    # Validate the required fields
    if not email:
        return jsonify({'message': 'Email is required'}), 400
    if not name:
        return jsonify({'message': 'Name is required'}), 400
    if not password:
        return jsonify({'message': 'Password is required'}), 400
    if not address:
        return jsonify({'message': 'Address is required'}), 400
    if not pincode:
        return jsonify({'message': 'Pincode is required'}), 400
    if not phone_number:
        return jsonify({'message': 'Phone number is required'}), 400
    if not service_type:
        return jsonify({'message': 'Service type is required'}), 400
    if not experience:
        return jsonify({'message': 'Experience is required'}), 400
    if not document:
        return jsonify({'message': 'Document is required'}), 400

    # Save the document if the file is provided
    filename = secure_filename(document.filename)  # Ensure the filename is safe
    saved_document_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    # Save the document to the server
    document.save(saved_document_path)

    # Create a new professional user entry
    user = user_datastore.create_user(
        email=email,
        name=name,
        password=password,
        address=address,
        pincode=pincode,
        phone_number=phone_number,
        service_type=service_type,
        experience=experience,
        document_path=saved_document_path  # Store the document path in the database
    )
    user_datastore.add_role_to_user(user, 'professional')
    db.session.commit()

    return jsonify({'message': 'Professional created successfully'}), 201


@app.route('/signin', methods=['POST'])
def signin():
    data = request.json
    email = data.get('email')
    if not email:
        return {"status": "please provide an email"}, 400
    password = data.get('password')
    if not password:
        return {"status": "please provide a password"}, 400
    user = user_datastore.find_user(email=email)
    if user and user.password == password:
        token = user.get_auth_token()
        return {"status": "success in loggin", "authToken": token, "role": user.roles[0].name}, 200
    return {"status": "Invalid credentials"}, 401

@cache.cached(timeout=50, key_prefix='all_categories')
@app.route('/all_categories', methods=['GET'])
# @roles_accepted('admin', 'professional', 'customer')
# @auth_token_required
# @cache.cached(timeout=50)

def get_categories():
    categories = Category.get_all_categories()
    return jsonify([category.serialize() for category in categories])

@app.route('/category', methods=['GET'])
@roles_accepted('admin', 'professional', 'customer')
@auth_token_required
def get_category():
    data = request.get_json()
    id = data.get('id')
    # id = request.json.get('id')
    category = Category.get_category_by_id(id)
    if not category:
        return jsonify({'message': 'Category not found'}), 404
    return jsonify(category.serialize())

@app.route('/services/category/<int:category_id>', methods=['GET'])
@roles_accepted('admin', 'professional', 'customer')
@auth_token_required
def get_services_by_category(category_id):
    services = Service.query.filter_by(category_id=category_id).all()
    return jsonify([s.serialize() for s in services])

# Route to add a category - requires admin role
@app.route('/add_category', methods=['POST'])
@roles_required('admin')
def add_category():
    data = request.get_json()
    name = data.get('name')
    description = data.get('description', '')

    if not name:
        return jsonify({'message': 'Name is required'}), 400
    
    if Category.query.filter_by(name=name).first():
        return jsonify({'message': 'Category already exists'}), 400

    category = Category(name=name, description=description)
    db.session.add(category)
    db.session.commit()

    # Clear the cache for all categories
    cache.delete('all_categories')

    return jsonify({"message": "Category added successfully"}), 201

# Route for customer to request a service
@app.route('/request_service', methods=['POST'])
@roles_accepted('customer')
@auth_token_required
def request_service():
    data = request.get_json()
    service_id = data.get('service_id')
    service = Service.get_service_by_id(service_id)
    if not service:
        return jsonify({'message': 'Service not found'}), 404
    customer_id = current_user.id
    professional_id = None
    new_request = ServiceRequest(customer_id=customer_id, service_id=service_id, professional_id=professional_id)
    db.session.add(new_request)
    db.session.commit()
    return jsonify({'message': 'Service requested successfully'}), 201

# Route to retrieve the currently logged-in customer's profile information
@app.route('/customer/profile', methods=['GET'])
@roles_accepted('customer', 'professional', 'admin')
@auth_token_required
def get_customer_profile():
    try:
        customer_id = current_user.id
        customer = User.query.get(customer_id)
        return jsonify(customer.serialize()), 200
    except Exception as e:
        return jsonify({"error": "Unable to fetch customer profile", "details": str(e)}), 500

# Route to update the currently logged-in customer's profile information
@app.route('/customer/profile', methods=['PUT'])
@roles_accepted('customer', 'admin')
@auth_token_required
def update_customer_profile():
    data = request.get_json()
    customer_id = current_user.id
    customer = User.query.get(customer_id)
    if not customer:
        return jsonify({"message": "Customer not found"}), 404
    customer.name = data.get('name', customer.name)
    customer.address = data.get('address', customer.address)
    customer.pincode = data.get('pincode', customer.pincode)
    customer.phone_number = data.get('phone_number', customer.phone_number)
    db.session.commit()
    return jsonify({"message": "Customer profile updated successfully"}), 200


@app.route('/customer/<int:customer_id>', methods=['GET'])
def get_customer_details(customer_id):
    """
    Fetch customer details by customer_id.
    """
    try:
        customer = User.query.filter_by(id=customer_id).first()
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404
        return jsonify(customer.serialize()), 200
    except Exception as e:
        return jsonify({'error': 'An error occurred while fetching customer details', 'details': str(e)}), 500

@app.route('/professional/profile', methods=['PUT'])
@roles_accepted('professional', 'admin')
@auth_token_required
def update_professional_profile():
    data = request.get_json()
    professional_id = current_user.id
    professional = User.query.get(professional_id)
    if not professional:
        return jsonify({"message": "Professional not found"}), 404
    professional.name = data.get('name', professional.name)
    professional.address = data.get('address', professional.address)
    professional.pincode = data.get('pincode', professional.pincode)
    professional.phone_number = data.get('phone_number', professional.phone_number)
    professional.experience = data.get('experience', professional.experience)
    db.session.commit()
    return jsonify({"message": "Professional profile updated successfully"}), 200

# Route to Searches for services based on a given search query
@app.route('/search_services', methods=['POST'])
@roles_accepted('admin', 'professional', 'customer')
@auth_token_required
def search_services():
    data = request.get_json()
    query = data.get('query')
    services = Service.query.filter(Service.name.ilike(f'%{query}%')).all()
    return jsonify([s.serialize() for s in services])   

# Route to book a service - requires customer role
@app.route('/book_service', methods=['POST'])
@roles_accepted('customer')
@auth_token_required
def book_service():
    data = request.get_json()
    service_id = data.get('service_id')
    service = Service.query.get(service_id)
    if not service:
        return jsonify({'message': 'Service not found'}), 404
    customer_id = current_user.id
    professional_id = None
    new_request = ServiceRequest(customer_id=customer_id, service_id=service_id, professional_id=professional_id)
    db.session.add(new_request)
    db.session.commit()
    return jsonify({'message': 'Service booked successfully'}), 201

# Route to cancel a service request - requires customer role
@app.route('/cancel_service_request', methods=['POST'])
@roles_accepted('customer')
@auth_token_required
def cancel_service_request():
    data = request.get_json()
    request_id = data.get('request_id')

    if not request_id:
        return jsonify({'message': 'Request ID is required'}), 400
    
    service_request = ServiceRequest.query.get(request_id)
    if not service_request:
        return jsonify({'message': 'Service request not found'}), 404
    
    if service_request.customer_id != current_user.id:
        return jsonify({'message': 'You are not authorized to cancel this request'}), 403
    
    #Change the status of the service request to cancelled
    service_request.status = 'Cancelled'

    
    db.session.commit()
    return jsonify({'message': 'Service request cancelled successfully'}), 200

# Route to rate and review a professional - requires customer role
@app.route('/rate_professional', methods=['POST'])
@roles_accepted('customer')
@auth_token_required
def rate_professional():
    data = request.get_json()
    customer_id = current_user.id
    professional_id = data.get('professional_id')
    rating = data.get('rating')
    review_text = data.get('review_text')

    # Validate the rating
    if not rating or rating < 1 or rating > 5:
        return jsonify({'message': 'Rating must be between 1 and 5'}), 400
    
    review = Review(customer_id=customer_id, professional_id=professional_id, rating=rating, review_text=review_text)

    db.session.add(review)
    db.session.commit()
    return jsonify({'message': 'Review submitted successfully'}), 200

@app.route('/professional/<int:professional_id>/rating', methods=['GET'])
@roles_accepted('admin', 'professional', 'customer')
@auth_token_required
def get_professional_rating(professional_id):
    # Logic to calculate and return the average rating
    professional = User.query.get(professional_id)
    if not professional:
        return jsonify({"error": "Professional not found"}), 404

    # Assuming `ratings` is a list of ratings for the professional
    average_rating = professional.get_average_rating()

    return jsonify({"average_rating": average_rating, "professional_name": professional.name, "professional_phone": professional.phone_number}), 200

@app.route('/service/<int:service_id>', methods=['GET'])
@roles_accepted('admin', 'professional', 'customer')
@auth_token_required
def get_service_details(service_id):
    """
    Fetch service details by service_id.
    """
    try:
        service = Service.query.filter_by(id=service_id).first()
        if not service:
            return jsonify({'error': 'Service not found'}), 404
        return jsonify(service.serialize()), 200
    except Exception as e:
        return jsonify({'error': 'An error occurred while fetching service details', 'details': str(e)}), 500

@app.route('/professional_service_requests', methods=['GET'])
@roles_accepted('professional')
@auth_token_required
def get_professional_service_requests():
    try:
        professional = current_user
        professional_service_type = professional.service_type

        # Query to fetch service requests for the professional's service type
        service_requests = (
            ServiceRequest.query
            .join(Service, ServiceRequest.service_id == Service.id)
            .join(Category, Service.category_id == Category.id)
            .filter(
                Category.name == professional_service_type,
                ServiceRequest.status.in_(['Pending', 'Accepted'])
            )
            .all()
        )

        # Format the response data
        formatted_requests = [
            {
                'id': request.id,
                'customer_name': request.customer.name if request.customer else None,
                'customer_address': request.customer.address if request.customer else None,
                'customer_pincode': request.customer.pincode if request.customer else None,
                'customer_phone_number': request.customer.phone_number if request.customer else None,
                # 'customer_email': request.customer.email if request.customer else None,
                'service_name': request.service.name if request.service else None,
                'service_description': request.service.description if request.service else None,
                'request_date': request.request_date,
                'service_price': request.service.price if request.service else None,
                'status': request.status
            }
            for request in service_requests
        ]

        return jsonify(formatted_requests), 200

    except Exception as e:
        return jsonify({"error": "Unable to fetch service requests", "details": str(e)}), 500

# Route to accept a service request - requires professional role
@app.route('/accept_service_request', methods=['POST'])
@roles_accepted('professional')
@auth_token_required
def accept_service_request():

    data = request.get_json()
    request_id = data.get('request_id')
    service_request = ServiceRequest.query.get(request_id)
    if not service_request:
        return jsonify({'message': 'Service request not found'}), 404
    professional = current_user
    if service_request.service.category.name != professional.service_type:
        return jsonify({'message': 'Service request does not match professional service type'}), 400
    service_request.professional_id = professional.id
    service_request.status = 'Accepted'
    db.session.commit()
    return jsonify({'message': 'Service request accepted successfully'}), 200

# Route to reject a service request - requires professional role
@app.route('/reject_service_request', methods=['POST'])
@roles_accepted('professional')
@auth_token_required
def reject_service_request():
    data = request.get_json()
    request_id = data.get('request_id')
    service_request = ServiceRequest.query.get(request_id)
    if not service_request:
        return jsonify({'message': 'Service request not found'}), 404
    professional = current_user
    if service_request.service.category.name != professional.service_type:
        return jsonify({'message': 'Service request does not match professional service type'}), 400
    service_request.professional_id = professional.id
    service_request.status = 'Rejected'
    db.session.commit()
    return jsonify({'message': 'Service request rejected successfully'}), 200

@app.route('/complete_service_request', methods=['POST'])
@roles_accepted('professional')
@auth_token_required
def complete_service_request():
    data = request.get_json()
    request_id = data.get('request_id')
    service_request = ServiceRequest.query.get(request_id)
    if not service_request:
        return jsonify({'message': 'Service request not found'}), 404
    professional = current_user
    if service_request.professional_id != professional.id:
        return jsonify({'message': 'You are not authorized to complete this request'}), 403
    service_request.status = 'Completed'
    db.session.commit()
    return jsonify({'message': 'Service request completed successfully'}), 200

@app.route('/professional_service_requests_history', methods=['GET'])
@roles_accepted('professional')
@auth_token_required
def get_service_requests_history():
    try:
        professional_id = current_user.id
        from sqlalchemy import and_
        service_requests = ServiceRequest.query.filter(and_(ServiceRequest.professional_id == professional_id, ServiceRequest.status.in_(['Rejected', 'Completed']))).all()

        serialized_requests = [
        {
            'id': request.id,
            'customer_name': request.customer.name,
            'service_name': request.service.name,
            'request_date': request.request_date,
            'status': request.status,
            'customer_review': request.customer_review
        }
        for request in service_requests
    ] 
        
        return jsonify(serialized_requests), 200
    except Exception as e:
        return jsonify({"error": "Unable to fetch request history", "details": str(e)}), 500

# Route to fetch a customer's service requests history (Requested, Assigned, Closed)
@app.route('/service_requests', methods=['GET'])
@roles_accepted('customer', 'admin')
@auth_token_required
def get_service_requests():
    try:
        customer_id = current_user.id
        service_requests = ServiceRequest.query.filter_by(customer_id=customer_id).all()
        return jsonify([sr.serialize() for sr in service_requests]), 200
    except Exception as e:
        return jsonify({"error": "Unable to fetch request history", "details": str(e)}), 500

# Route to fetch all the service requests - requires admin role
@app.route('/all_service_requests', methods=['GET'])
@roles_required('admin')
@auth_token_required
def get_all_service_requests():
    try:
        service_requests = ServiceRequest.query.all()
        return jsonify([sr.serialize() for sr in service_requests]), 200
    except Exception as e:
        return jsonify({"error": "Unable to fetch request history", "details": str(e)}), 500
    
if __name__ == '__main__':
    app.run(debug=True)