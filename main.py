import requests
from bs4 import BeautifulSoup
import sys
from typing import Tuple, Optional
import time
from dotenv import load_dotenv
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone
from dateutil import parser
import pytz
import hashlib


# Load environment variables from credentials.env file
load_dotenv('credentials.env')

# Retrieve credentials from environment variables
username = os.getenv('USERNAME')
password = os.getenv('PASSWORD')
client_id = os.getenv('CLIENT_ID')
client_secret = os.getenv('CLIENT_SECRET')
refresh_token = os.getenv('REFRESH_TOKEN')
PUSHOVER_TOKEN = os.getenv('PUSHOVER_TOKEN')
PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')

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
    appointment_rows = soup.find_all('tr', style='color: black; background: whitesmoke')[:8]  # Only take the first 8 entries

    for row in appointment_rows:
        columns = row.find_all('td')
        if len(columns) == 5:
            date_element = row.find_previous('tr', style='color: white; background: #9BC7E6; width: 100px')
            date = date_element.find_all('td')[1].get_text(strip=True) if date_element else ''

            time_range = columns[0].get_text(strip=True).replace('\n', ' ')
            start_time = time_range[:5]  # First 5 characters for start time
            end_time = time_range[5:].strip()  # Remaining characters for end time

            # Get studio name
            studio_name_element = columns[1].find('b')
            studio_name = studio_name_element.get_text(strip=True) if studio_name_element else ''

            # Get all text from columns[1], excluding the studio name
            column_texts = list(columns[1].stripped_strings)
            # Remove the studio name from the list
            if studio_name in column_texts:
                column_texts.remove(studio_name)

            # Initialize address and regie
            address = ''
            regie = ''

            for text in column_texts:
                if text.startswith('Regie:'):
                    regie = text
                else:
                    address += text + ' '

            address = address.strip()

            appointment = {
                'date': date,
                'start_time': start_time,
                'end_time': end_time,
                'studio_name': studio_name,
                'address': address,
                'regie': regie
            }
            appointments.append(appointment)

    # Log the extracted appointments
    for appointment in appointments:
        print(f"Appointment: {appointment['date']}, {appointment['start_time']} - {appointment['end_time']}, {appointment['studio_name']}, {appointment['address']}, {appointment['regie']}")
else:
    print('Login failed. Please check your credentials.')
    
def login_with_retry(
    session: requests.Session,
    base_url: str,
    login_url: str,
    username: str,
    password: str,
    max_retries: int = 3,
    retry_delay: int = 5
) -> Tuple[bool, Optional[list]]:
    """
    Attempts to login with retry mechanism.
    
    Args:
        session: requests Session object
        base_url: Base URL for the website
        login_url: Login endpoint URL
        username: Login username
        password: Login password
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
    
    Returns:
        Tuple of (success_status: bool, appointments: Optional[list])
    """
    appointments = []
    
    for attempt in range(max_retries):
        try:
            print(f"Login attempt {attempt + 1}/{max_retries}...")
            
            # Get CSRF token
            response = session.get(base_url)
            response.raise_for_status()  # Raise exception for bad status codes
            
            soup = BeautifulSoup(response.text, 'html.parser')
            csrf_token_element = soup.find('input', {'name': '_token'})
            
            if not csrf_token_element:
                print(f"Attempt {attempt + 1}: Failed to retrieve CSRF token")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                continue
                
            csrf_token = csrf_token_element['value']
            print(f"Retrieved CSRF token: {csrf_token}")
            
            # Prepare login payload
            login_payload = {
                'username': username,
                'password': password,
                '_token': csrf_token
            }
            
            # Attempt login
            login_response = session.post(login_url, data=login_payload)
            login_response.raise_for_status()
            
            # Verify successful login by checking for 'Termine' in response
            if 'Termine' in login_response.text:
                print("Login successful!")
                
                # Get appointments
                appointments_response = session.get(f"{base_url}/events?is_app=0")
                appointments_response.raise_for_status()
                
                # Parse appointments (keeping your existing parsing logic)
                appointments = parse_appointments(appointments_response.text)
                return True, appointments
            else:
                print(f"Attempt {attempt + 1}: Login response didn't contain expected content")
                
        except requests.RequestException as e:
            print(f"Attempt {attempt + 1} failed with error: {str(e)}")
        
        if attempt < max_retries - 1:
            print(f"Waiting {retry_delay} seconds before next attempt...")
            time.sleep(retry_delay)
    
    print(f"Failed to login after {max_retries} attempts")
    return False, None

def parse_appointments(html_content: str) -> list:
    """
    Parses the appointments from the HTML content.
    Keeps your existing appointment parsing logic.
    """
    appointments = []
    soup = BeautifulSoup(html_content, 'html.parser')
    appointment_rows = soup.find_all('tr', style='color: black; background: whitesmoke')[:8]

    for row in appointment_rows:
        columns = row.find_all('td')
        if len(columns) == 5:
            date_element = row.find_previous('tr', style='color: white; background: #9BC7E6; width: 100px')
            date = date_element.find_all('td')[1].get_text(strip=True) if date_element else ''

            time_range = columns[0].get_text(strip=True).replace('\n', ' ')
            start_time = time_range[:5]
            end_time = time_range[5:].strip()

            studio_name_element = columns[1].find('b')
            studio_name = studio_name_element.get_text(strip=True) if studio_name_element else ''

            column_texts = list(columns[1].stripped_strings)
            if studio_name in column_texts:
                column_texts.remove(studio_name)

            address = ''
            regie = ''

            for text in column_texts:
                if text.startswith('Regie:'):
                    regie = text
                else:
                    address += text + ' '

            address = address.strip()

            appointment = {
                'date': date,
                'start_time': start_time,
                'end_time': end_time,
                'studio_name': studio_name,
                'address': address,
                'regie': regie
            }
            appointments.append(appointment)
    
    return appointments

def authenticate_google_api():
    print("Authenticating Google Calendar API...")
    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=['https://www.googleapis.com/auth/calendar']
    )
    service = build('calendar', 'v3', credentials=creds)
    return service

def fetch_future_events(service):
    now = datetime.now(timezone.utc).isoformat()
    print("Fetching future events from Google Calendar...")
    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        privateExtendedProperty='createdBySynchronScript=true',
        maxResults=100,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    # Print complete event details for debugging
    for event in events:
        print(f"Fetched event: {event['summary']}")
        print(f"Description: {event.get('description', 'No description')}")
        print(f"Location: {event.get('location', 'No location')}")
        print(f"Extended Properties: {event.get('extendedProperties', {})}")
        print("---")

    return events

def create_google_calendar_event(service, appointment):
    appointment_id = generate_appointment_id(appointment)
    event = {
        'summary': appointment['studio_name'],
        'location': appointment['address'],
        'description': appointment.get('regie', ''),
        'start': {
            'dateTime': appointment['start_datetime'].isoformat(),
            'timeZone': 'Europe/Berlin',
        },
        'end': {
            'dateTime': appointment['end_datetime'].isoformat(),
            'timeZone': 'Europe/Berlin',
        },
        'extendedProperties': {
            'private': {
                'createdBySynchronScript': 'true',
                'appointment_id': appointment_id
            }
        }
    }

    event = service.events().insert(calendarId='primary', body=event).execute()
    print(f"Event created: {event.get('htmlLink')}")
    
    # Send push notification for new appointment
    send_push_notification(
        "New Appointment Added",
        format_notification_message(appointment),
        priority=1
    )

def update_google_calendar_event(service, event_id, appointment):
    appointment_id = appointment['appointment_id']
    # Print debug information before update
    print(f"Updating event {event_id} with new details:")
    print(f"Studio: {appointment['studio_name']}")
    print(f"Location: {appointment['address']}")
    print(f"Regie: {appointment.get('regie', 'No regie')}")

    event = {
        'summary': appointment['studio_name'],
        'location': appointment['address'],
        'description': appointment.get('regie', ''),
        'start': {
            'dateTime': appointment['start_datetime'].isoformat(),
            'timeZone': 'Europe/Berlin',
        },
        'end': {
            'dateTime': appointment['end_datetime'].isoformat(),
            'timeZone': 'Europe/Berlin',
        },
        'extendedProperties': {
            'private': {
                'createdBySynchronScript': 'true',
                'appointment_id': appointment_id
            }
        }
    }

    try:
        updated_event = service.events().update(
            calendarId='primary',
            eventId=event_id,
            body=event
        ).execute()

        print(f"Event updated successfully: {updated_event.get('htmlLink')}")
        print(f"Updated event description: {updated_event.get('description', 'No description')}")

        # Send push notification for updated appointment
        send_push_notification(
            "Appointment Updated",
            format_notification_message(appointment, action="updated"),
            priority=1
        )

        return updated_event

    except Exception as e:
        print(f"Error updating event: {e}")
        return None


def needs_update(event, appointment):
    event_start = parser.isoparse(event['start']['dateTime']).astimezone(pytz.timezone('Europe/Berlin'))
    event_end = parser.isoparse(event['end']['dateTime']).astimezone(pytz.timezone('Europe/Berlin'))

    appointment_start = appointment['start_datetime']
    appointment_end = appointment['end_datetime']

    current_regie = event.get('description', '').strip()
    new_regie = appointment.get('regie', '').strip()

    # Print debug information
    print(f"Checking if event {appointment} needs update:")
    # print(f"Start times match: {event_start == appointment_start}")
    # print(f"End times match: {event_end == appointment_end}")
    # print(f"Locations match: {event.get('location', '') == appointment['address']}")
    # print(f"Current regie: '{current_regie}'")
    # print(f"New regie: '{new_regie}'")
    # print(f"Regie matches: {current_regie == new_regie}")

    return (
        event_start != appointment_start or
        event_end != appointment_end or
        event.get('location', '') != appointment['address'] or
        current_regie != new_regie
    )

def send_push_notification(title, message, priority=0):
    """
    Send push notification using Pushover.
    Priority: -2 to 2 (-2 is lowest, 2 is highest/emergency)
    """
    print(f"Sending push notification: {title}")
    
    payload = {
        'token': PUSHOVER_TOKEN,
        'user': PUSHOVER_USER_KEY,
        'title': title,
        'message': message,
        'priority': priority,
        'sound': 'pushover'
    }
    
    response = requests.post(
        'https://api.pushover.net/1/messages.json',
        data=payload
    )
    
    if response.status_code == 200:
        print("Push notification sent successfully")
    else:
        print(f"Failed to send push notification: {response.text}")

def format_notification_message(appointment, action="added"):
    """
    Format the notification message for an appointment.
    """
    message = (
        f"Appointment {action}:\n"
        f"Studio: {appointment['studio_name']}\n"
        f"Date: {appointment['date']}\n"
        f"Time: {appointment['start_time']} - {appointment['end_time']}\n"
        f"Location: {appointment['address']}"
    )
    
    if appointment.get('regie'):  # Add regie information if available
        message += f"\nRegie: {appointment['regie']}"
        
    return message
        
def generate_appointment_id(appointment):
    # Concatenate date, studio_name, regie
    id_string = f"{appointment['date']}_{appointment['studio_name']}_{appointment.get('regie', '')}"
    # Generate a hash
    appointment_id = hashlib.md5(id_string.encode('utf-8')).hexdigest()
    return appointment_id     
        
def delete_google_calendar_event(service, event_id):
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        print(f"Event {event_id} deleted successfully.")
    except Exception as e:
        print(f"Failed to delete event {event_id}: {e}")
        
        
def format_notification_message_from_key(key, action="cancelled"):
    date, start_time, studio_name, regie = key
    message = (
        f"Appointment {action}:\n"
        f"Studio: {studio_name}\n"
        f"Date: {date}\n"
        f"Time: {start_time}"
    )
    if regie:
        message += f"\nRegie: {regie}"
    return message

# __________________________________________________________________

def main():
    print("Starting main function...")
    
    # Create a session
    session = requests.Session()
    
    # Attempt login with retry mechanism
    login_success, appointments = login_with_retry(
        session=session,
        base_url=base_url,
        login_url=login_url,
        username=username,
        password=password,
        max_retries=3,
        retry_delay=5
    )
    
    if not login_success:
        print("Failed to login after all retry attempts. Exiting script.")
        sys.exit(1)
    
    if not appointments:
        print("No appointments found. Exiting script.")
        sys.exit(0)
        
    # Continue with the rest of your existing main() function...
    tz = pytz.timezone('Europe/Berlin')
    current_date = datetime.now(tz)
    future_appointments = []

    for appointment in appointments:
        start_datetime_str = f"{appointment['date']} {appointment['start_time']}"
        end_datetime_str = f"{appointment['date']} {appointment['end_time']}"

        start_datetime_naive = datetime.strptime(start_datetime_str, '%d.%m.%Y %H:%M')
        end_datetime_naive = datetime.strptime(end_datetime_str, '%d.%m.%Y %H:%M')

        start_datetime = tz.localize(start_datetime_naive)
        end_datetime = tz.localize(end_datetime_naive)

        if start_datetime >= current_date:
            appointment['start_datetime'] = start_datetime
            appointment['end_datetime'] = end_datetime
            appointment['appointment_id'] = generate_appointment_id(appointment)
            future_appointments.append(appointment)

    service = authenticate_google_api()
    future_events = fetch_future_events(service)

    # Only proceed with calendar operations if we have appointments
    if future_appointments:
        process_calendar_events(service, future_appointments, future_events, current_date)
    else:
        print("No future appointments found. Skipping calendar operations.")

def process_calendar_events(service, future_appointments, future_events, current_date):
    """
    Process calendar events with proper error handling
    """
    appointment_id_to_appointment = {appt['appointment_id']: appt for appt in future_appointments}
    event_appointment_id_to_event = {}
    
    for event in future_events:
        appointment_id = event.get('extendedProperties', {}).get('private', {}).get('appointment_id', '')
        event_start = parser.isoparse(event['start']['dateTime'])
        
        if appointment_id and event_start >= current_date:
            event_appointment_id_to_event[appointment_id] = event

    # Only delete events if we successfully fetched new appointments
    events_to_delete = set(event_appointment_id_to_event.keys()) - set(appointment_id_to_appointment.keys())
    for appointment_id in events_to_delete:
        event = event_appointment_id_to_event[appointment_id]
        delete_google_calendar_event(service, event['id'])
        
        date_str = parser.isoparse(event['start']['dateTime']).strftime('%d.%m.%Y')
        start_time_str = parser.isoparse(event['start']['dateTime']).strftime('%H:%M')
        key = (date_str, start_time_str, event.get('summary', ''), event.get('description', ''))
        send_push_notification(
            "Appointment Cancelled",
            format_notification_message_from_key(key, action="cancelled"),
            priority=1
        )

    for appointment_id, appointment in appointment_id_to_appointment.items():
        if appointment_id in event_appointment_id_to_event:
            event = event_appointment_id_to_event[appointment_id]
            if needs_update(event, appointment):
                print(f"Updated required for: {appointment}")
                update_google_calendar_event(service, event['id'], appointment)
        else:
            create_google_calendar_event(service, appointment)

if __name__ == "__main__":
    try:
        main()
        print("Main function executed successfully.")
    except Exception as e:
        print(f"Script failed with error: {str(e)}")
        sys.exit(1)