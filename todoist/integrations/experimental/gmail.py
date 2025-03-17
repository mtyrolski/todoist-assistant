import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def main():
    """Shows basic usage of the Gmail API.
    Lists the user's unread emails from the last 4 weeks.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)

    # Call the Gmail API
    now = datetime.datetime.utcnow()
    four_weeks_ago = (now - datetime.timedelta(weeks=4)).isoformat() + 'Z'    # 'Z' indicates UTC time

    # Fetch unread emails from the last 4 weeks
    results = service.users().messages().list(userId='me', q=f'is:unread after:{four_weeks_ago}').execute()
    messages = results.get('messages', [])

    if not messages:
        print('No unread messages found.')
    else:
        print('Unread messages:')
        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id']).execute()
            print(f"From: {msg['payload']['headers'][0]['value']}")
            print(f"Subject: {msg['payload']['headers'][1]['value']}")
            print(f"Snippet: {msg['snippet']}")
            print('-' * 40)


if __name__ == '__main__':
    main()
