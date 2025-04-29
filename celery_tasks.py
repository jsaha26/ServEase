import csv
from app import app_celery
from celery_context import appContext
from mailer import mailer
from models import ServiceRequest, User
from datetime import datetime, timedelta
from flask_mail import Message
from io import StringIO
import os

# A Celery task to add two numbers
@app_celery.task(base=appContext)
def add(a, b):
    import time
    time.sleep(5)
    return a + b

@app_celery.task(base=appContext)
def hello_world():
    print('Hello, World!')
    return 'Hello, World!'

@app_celery.task(base=appContext)
def hello_world_with_name(name):
    print(f'Hello, {name}!')
    return f'Hello, {name}!'

@app_celery.task(base=appContext)
def search_category(a):
    from models import Category
    cat = Category.query.filter_by(id=a).first()
    if cat:  
        print("name", cat.name, "desc", cat.description)
        return cat.id
    else:
        return "Not Found"
    
@app_celery.task(base=appContext)
def test_email():
    from models import User
    all_users = User.query.all()
    for user in all_users:
        if not user.roles[0].name == 'admin':
            print(user.email)
            from flask_mail import Message
            email_receiver = user.email
            email_subject = "Test Email"
            email_body = "This is a test email"
            # from mailer import mailer
            msg = Message(email_subject, recipients=[email_receiver])
            msg.body = email_body
            mailer.send(msg)

# # Task to remind service professional to complete their pending service

@app_celery.task(base=appContext)
def remind_professionals_to_complete_requests():
    """
    Celery task to remind service professionals about in-progress requests.
    """
    # Query all in-progress requests
    in_progress_requests = ServiceRequest.query.filter_by(status="Accepted").all()

    if not in_progress_requests:
        print("No in-progress service requests found.")
        return "No reminders sent. No in-progress requests found."

    for request in in_progress_requests:
        professional = request.professional
        if professional and professional.email:
            # Prepare the reminder message
            email_subject = "Reminder: Complete Your Service Requests"
            email_body = (
                f"Dear {professional.name},\n\n"
                f"You have an in-progress service request for '{request.service.name}'. "
                f"Please ensure it is completed promptly.\n\n"
                f"Request Details:\n"
                f"- Service: {request.service.name}\n"
                f"- Customer: {request.customer.name}\n"
                f"- Request Date: {request.request_date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Thank you for your commitment to excellent service!\n"
                f"Best Regards,\nYour Team"
            )

            # Send the email
            try:
                msg = Message(email_subject, recipients=[professional.email])
                msg.body = email_body
                mailer.send(msg)
                print(f"Reminder sent to {professional.email} for request ID {request.id}.")
            except Exception as e:
                print(f"Failed to send reminder to {professional.email}: {str(e)}")

    return f"Reminders sent for {len(in_progress_requests)} in-progress service requests."


@app_celery.task(base=appContext)
def send_monthly_activity_report():
    # Fetch the start and end dates for the last month
    today = datetime.utcnow()
    first_day_of_last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    last_day_of_last_month = today.replace(day=1) - timedelta(days=1)
    
    # Generate reports for each customer
    customers = User.query.filter(User.roles.any(name="customer")).all()
    
    for customer in customers:
        service_requests = ServiceRequest.query.filter(
            ServiceRequest.customer_id == customer.id,
            ServiceRequest.request_date.between(first_day_of_last_month, last_day_of_last_month)
        ).all()
        
        # Generate the HTML content for the report
        html_report = generate_activity_report(customer, service_requests, first_day_of_last_month, last_day_of_last_month)
        
        # Send the email
        send_email(
            recipient=customer.email,
            subject="Monthly Activity Report",
            html_body=html_report
        )

def generate_activity_report(customer, service_requests, start_date, end_date):
    """
    Generate an HTML report of the customer's activity.
    """
    services_requested = len(service_requests)
    services_closed = len([req for req in service_requests if req.status == "Completed"])
    
    html_content = f"""
    <html>
        <body>
            <h1>Monthly Activity Report</h1>
            <p><strong>Customer Name:</strong> {customer.name}</p>
            <p><strong>Report Period:</strong> {start_date.strftime('%B %d, %Y')} to {end_date.strftime('%B %d, %Y')}</p>
            
            <h2>Service Summary</h2>
            <ul>
                <li>Total Services Requested: {services_requested}</li>
                <li>Total Services Completed: {services_closed}</li>
            </ul>
            
            <h2>Detailed Activity</h2>
            <table border="1" cellpadding="5" cellspacing="0">
                <tr>
                    <th>Service Name</th>
                    <th>Status</th>
                    <th>Date Requested</th>
                    <th>Date Completed</th>
                </tr>
    """
    for req in service_requests:
        service = req.service
        html_content += f"""
        <tr>
            <td>{service.name}</td>
            <td>{req.status}</td>
            <td>{req.request_date.strftime('%Y-%m-%d')}</td>
            <td>{req.request_date.strftime('%Y-%m-%d') if req.status == 'Completed' else 'N/A'}</td>
        </tr>
        """
    
    html_content += """
            </table>
        </body>
    </html>
    """
    return html_content

def send_email(recipient, subject, html_body):
    """
    Sends an email using Flask-Mail.
    """
    msg = Message(subject, recipients=[recipient])
    msg.html = html_body
    mailer.send(msg)

# Task to export closed service requests to a CSV file and email it to the admin

@app_celery.task(base=appContext)
def export_closed_requests_to_csv():
    filename = f'closed_requests_{datetime.now().strftime("%Y%m%d%H%M%S")}.csv'
    static_dir = os.path.join(app_celery.root_path, 'static')  # Get absolute path to 'static' directory
    os.makedirs(static_dir, exist_ok=True)  # Ensure the directory exists
    filepath = os.path.join(static_dir, filename)
    
    # Query closed requests
    closed_requests = ServiceRequest.query.filter_by(status='Completed').all()
    
    # Write to CSV
    with open(filepath, 'w', newline='') as csvfile:
        fieldnames = ['service_id', 'customer_id', 'professional_id', 'date_of_request', 'remarks']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for request in closed_requests:
            writer.writerow({
                'service_id': request.id,
                'customer_id': request.customer_id,
                'professional_id': request.professional_id,
                'date_of_request': request.request_date,
                'remarks': request.remarks or ''  # Handle NoneType remarks
            })

    return filepath  # Return the absolute path