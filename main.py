import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

# Load environment variables from credentials.env file
load_dotenv('credentials.env')

# Retrieve credentials from environment variables
username = os.getenv('USERNAME')
password = os.getenv('PASSWORD')
client_id = os.getenv('CLIENT_ID')
client_secret = os.getenv('CLIENT_SECRET')
refresh_token = os.getenv('REFRESH_TOKEN')

print("Starting script execution...")

base_url = 'https://login.synchron.de'
login_url = 'https://login.synchron.de/login?is_app=0'
appointments_url = 'https://login.synchron.de/events?is_app=0'

# Create a session
session = requests.Session()

print("Created session. Sending GET request to base URL...")

# Send a GET request to the base URL to retrieve the CSRF token
response = session.get(base_url)
soup = BeautifulSoup(response.text, 'html.parser')
csrf_token_element = soup.find('input', {'name': '_token'})
csrf_token = csrf_token_element['value'] if csrf_token_element else ''

print(f"Retrieved CSRF token: {csrf_token}")

# Prepare the login payload
login_payload = {
    'username': username,
    'password': password,
    '_token': csrf_token
}

print("Sending POST request to login URL...")

# Send a POST request to the login URL with the login payload
login_response = session.post(login_url, data=login_payload)
print(f"Login response status: {login_response.status_code}")

appointments = []

# Check if the login was successful
if login_response.status_code == 200 and 'Termine' in login_response.text:
    print("Login successful. Sending GET request to appointments URL...")
    
    # Send a GET request to the appointments page
    appointments_response = session.get(appointments_url)
    appointments_html = appointments_response.text

    # Parse the HTML using BeautifulSoup
    soup = BeautifulSoup(appointments_html, 'html.parser')

    # Find all the appointment rows
    appointment_rows = soup.find_all('tr', style='color: black; background: whitesmoke')[:5]  # Only take the first 5 entries

    for row in appointment_rows:
        columns = row.find_all('td')
        if len(columns) == 5:
            date_element = row.find_previous('tr', style='color: white; background: #9BC7E6; width: 100px')
            date = date_element.find_all('td')[1].get_text(strip=True) if date_element else ''

            time_range = columns[0].get_text(strip=True).replace('\n', ' ')
            start_time = time_range[:5]  # First 5 characters for start time
            end_time = time_range[5:].strip()  # Remaining characters for end time

            studio_name_element = columns[1].find('b')
            studio_name = studio_name_element.get_text(strip=True) if studio_name_element else ''

            address = columns[1].get_text(strip=True).replace(studio_name, '').strip()

            appointment = {
                'date': date,
                'start_time': start_time,
                'end_time': end_time,
                'studio_name': studio_name,
                'address': address
            }
            appointments.append(appointment)

    # Log the extracted appointments
    for appointment in appointments:
        print(f"Appointment: {appointment['date']}, {appointment['start_time']} - {appointment['end_time']}, {appointment['studio_name']}, {appointment['address']}")
else:
    print('Login failed. Please check your credentials.')

def authenticate_google_api():
    print("Authenticating Google Calendar API...")
    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
    )
    service = build('calendar', 'v3', credentials=creds)
    return service

def fetch_future_events(service):
    now = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
    print("Fetching future events from Google Calendar...")
    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        maxResults=20, #30
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])
    return events

def event_exists(service, summary, start_time, end_time):
    time_min = (start_time - timedelta(minutes=1)).isoformat() + '+02:00'
    time_max = (end_time + timedelta(minutes=1)).isoformat() + '+02:00'
    
    print(f"Checking if event {summary}, Start: {start_time.isoformat() + '+02:00'}, End: {end_time.isoformat() + '+02:00'} already exists in Google Calendar...")
    events_result = service.events().list(
        calendarId='primary',
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    for event in events:
        event_start = event['start']['dateTime']
        event_end = event['end']['dateTime']
        event_summary = event['summary']

        # Print statements for debugging
        print(f"Comparing with event: {event_summary}, Start: {event_start}, End: {event_end}")
        if event_summary == summary and event_start == start_time.isoformat() + '+02:00' and event_end == end_time.isoformat() + '+02:00':
            return True
    return False

def create_google_calendar_event(service, summary, location, start_time, end_time):
    event = {
        'summary': summary,
        'location': location,
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'Europe/Berlin',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'Europe/Berlin',
        },
    }

    event = service.events().insert(calendarId='primary', body=event).execute()
    print(f"Event created: {event.get('htmlLink')}")

def main():
    print("Starting main function...")
    # Filter out past appointments
    current_date = datetime.now()
    future_appointments = []

    for appointment in appointments:
        start_datetime_str = f"{appointment['date']} {appointment['start_time']}"
        start_datetime = datetime.strptime(start_datetime_str, '%d.%m.%Y %H:%M')

        if start_datetime >= current_date:
            future_appointments.append(appointment)

    # Log the future appointments for testing
    print("Future appointments from Synchron.de:")
    for appointment in future_appointments:
        print(f"Date: {appointment['date']}, Start Time: {appointment['start_time']}, End Time: {appointment['end_time']}, Studio: {appointment['studio_name']}, Address: {appointment['address']}")

    # Authenticate Google Calendar API
    service = authenticate_google_api()

    # Fetch future events from Google Calendar
    future_events = fetch_future_events(service)
    print("Future events from Google Calendar:")
    for event in future_events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        print(f"Summary: {event['summary']}, Start: {start}, End: {end}")

    # Log the appointments that would get created
    print("Appointments to be created in Google Calendar:")
    for appointment in future_appointments:
        start_datetime_str = f"{appointment['date']} {appointment['start_time']}"
        end_datetime_str = f"{appointment['date']} {appointment['end_time']}"
        start_datetime = datetime.strptime(start_datetime_str, '%d.%m.%Y %H:%M')
        end_datetime = datetime.strptime(end_datetime_str, '%d.%m.%Y %H:%M')

        if not event_exists(service, appointment['studio_name'], start_datetime, end_datetime):
            create_google_calendar_event(service, appointment['studio_name'], appointment['address'], start_datetime, end_datetime)
        else:
            print(f"Event already exists: {appointment['studio_name']} on {appointment['date']} from {appointment['start_time']} to {appointment['end_time']} at {appointment['address']}")

if __name__ == "__main__":
    main()
    print("Main function executed successfully.")
