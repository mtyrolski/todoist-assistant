# Gmail Tasks Automation Setup

This guide explains how to set up the Gmail Tasks automation feature for Todoist Assistant, which automatically creates Todoist tasks from actionable emails.

## Overview

The Gmail Tasks automation:
- Fetches unread emails from the last week
- Identifies emails containing actionable items based on keywords
- Creates corresponding tasks in Todoist
- Avoids creating duplicate tasks
- Runs every hour by default

## Prerequisites

1. **Google Cloud Console Account**: You need access to Google Cloud Console to create a project and enable the Gmail API
2. **Gmail Account**: The Gmail account you want to monitor for tasks
3. **Todoist Assistant**: This feature requires the Todoist Assistant to be already set up with your Todoist API key

## Step 1: Create Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Note your project name/ID for later use

## Step 2: Enable Gmail API

1. In the Google Cloud Console, navigate to **APIs & Services > Library**
2. Search for "Gmail API"
3. Click on "Gmail API" and then click **Enable**

## Step 3: Create Credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth 2.0 Client IDs**
3. If prompted, configure the OAuth consent screen:
   - Choose **External** user type (unless you have a Google Workspace account)
   - Fill in the required fields:
     - App name: "Todoist Assistant Gmail Integration"
     - User support email: Your email address
     - Developer contact email: Your email address
   - Add your email to test users in the "Test users" section
4. For the OAuth 2.0 Client ID:
   - Application type: **Desktop application**
   - Name: "Todoist Assistant"
   - Click **Create**

## Step 4: Download Credentials

1. After creating the OAuth 2.0 Client ID, click the download button (⬇️) next to your credential
2. Save the downloaded JSON file as `gmail_credentials.json` in your Todoist Assistant root directory
3. The file should be in the same directory as your `.env` file

## Step 5: Configure the Automation

The Gmail Tasks automation is already configured in `configs/automations.yaml`. You can customize it by modifying:

```yaml
- _target_: todoist.automations.gmail_tasks.GmailTasksAutomation
  name: Gmail Tasks
  frequency_in_minutes: 60  # Run every hour (adjust as needed)
```

## Step 6: First Run and Authentication

1. Run the Todoist Assistant with automations:
   ```bash
   make update_env
   ```

2. The first time the Gmail automation runs, it will:
   - Open a web browser for OAuth authentication
   - Ask you to sign in to your Google account
   - Request permission to read your Gmail messages
   - Save authentication tokens to `gmail_token.json`

3. Grant the required permissions when prompted

## Configuration Options

### Automation Frequency

You can adjust how often the automation runs by modifying the `frequency_in_minutes` parameter in `configs/automations.yaml`:

```yaml
- _target_: todoist.automations.gmail_tasks.GmailTasksAutomation
  name: Gmail Tasks
  frequency_in_minutes: 30  # Run every 30 minutes
```

### Task Keywords

The automation identifies actionable emails based on keywords. You can modify the keywords by editing the `TASK_KEYWORDS` list in `todoist/automations/gmail_tasks.py`:

```python
TASK_KEYWORDS = [
    'todo', 'to do', 'action required', 'follow up', 'deadline', 'urgent',
    'reminder', 'task', 'complete', 'finish', 'review', 'approve',
    'respond', 'reply', 'meeting', 'call', 'schedule', 'due'
    # Add your custom keywords here
]
```

## How It Works

1. **Email Fetching**: The automation fetches unread emails from the last week
2. **Content Analysis**: Each email is analyzed for actionable keywords in the subject and snippet
3. **Task Creation**: Emails with actionable content are converted to Todoist tasks with:
   - **Content**: Email subject (cleaned up)
   - **Description**: Sender information and email snippet
   - **Priority**: Determined by urgency keywords (normal or high)
   - **Label**: `gmail-task` for easy identification
4. **Duplicate Prevention**: The automation checks existing tasks to avoid creating duplicates

## File Structure

After setup, your directory should contain:

```
todoist-assistant/
├── .env                          # Your Todoist API key
├── gmail_credentials.json        # Gmail API credentials (you create this)
├── gmail_token.json             # Auto-generated after first auth
├── configs/
│   └── automations.yaml         # Automation configuration
└── todoist/
    └── automations/
        └── gmail_tasks.py       # Gmail automation code
```

## Troubleshooting

### "Gmail credentials file not found" Error

- Ensure `gmail_credentials.json` is in the root directory
- Verify the file was downloaded correctly from Google Cloud Console
- Check that the file is not named `credentials.json` (it should be `gmail_credentials.json`)

### "Authentication failed" Error

- Delete `gmail_token.json` and try again
- Verify your Google account has access to the Gmail you want to monitor
- Check that you're added as a test user in the OAuth consent screen

### "No permission to read emails" Error

- Ensure you granted all requested permissions during OAuth flow
- Check that the Gmail API is enabled in your Google Cloud project
- Verify the OAuth consent screen is properly configured

### "Too many API calls" Error

- Reduce the `frequency_in_minutes` value in the configuration
- The Gmail API has rate limits; running too frequently may trigger them

## Security Notes

1. **Credentials Security**: Keep your `gmail_credentials.json` and `gmail_token.json` files secure and never commit them to version control
2. **Scope Limitation**: The automation only requests read-only access to Gmail (`gmail.readonly` scope)
3. **Local Processing**: All email processing happens locally; no email content is sent to external services
4. **Test Users**: During development, only users added to the OAuth consent screen can authenticate

## Manual Run

To manually trigger the Gmail Tasks automation without waiting for the scheduled run:

```bash
# Run all automations (including Gmail Tasks)
make update_env

# Or run specific automation through the dashboard
make run_dashboard
# Navigate to Control Panel and run "Gmail Tasks" automation
```

## Viewing Created Tasks

Tasks created by the Gmail automation will:
- Appear in your default Todoist project (usually Inbox)
- Have the label `gmail-task` for easy filtering
- Include email context in the task description
- Have appropriate priority based on email urgency keywords