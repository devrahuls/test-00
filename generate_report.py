import os
import json
import datetime
import requests
import sys

# Configurations
API_BASE_URL = "https://test-management.browserstack.com/api/v2"
PREVIOUS_STATE_FILE = "previous_state.json"
REPORTS_DIR = "reports"

# Credentials from Environment
USERNAME = os.environ.get("BROWSERSTACK_USERNAME")
ACCESS_KEY = os.environ.get("BROWSERSTACK_ACCESS_KEY")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
PROJECT_ID = os.environ.get("BROWSERSTACK_PROJECT_ID")  # Optional: If multiple projects exist

def get_auth():
    if not USERNAME or not ACCESS_KEY:
        print("Error: Missing BROWSERSTACK_USERNAME or BROWSERSTACK_ACCESS_KEY environment variables.")
        sys.exit(1)
    return (USERNAME, ACCESS_KEY)

def fetch_project_id():
    if PROJECT_ID:
        return PROJECT_ID
    
    response = requests.get(f"{API_BASE_URL}/projects", auth=get_auth())
    response.raise_for_status()
    projects = response.json()
    
    if not projects.get("projects"):
        print("Error: No projects found in BrowserStack Test Management.")
        sys.exit(1)
        
    # Default to the first project if not specified
    first_project = projects["projects"][0]
    print(f"Using Project: {first_project.get('name')} (ID: {first_project.get('id')})")
    return first_project.get('id')

def fetch_all_test_cases(project_id):
    test_cases = {}
    page = 1
    
    while True:
        # BrowserStack uses pagination, adjust 'limit' if needed per their docs
        response = requests.get(f"{API_BASE_URL}/projects/{project_id}/test-cases?page={page}&limit=100", auth=get_auth())
        response.raise_for_status()
        data = response.json()
        
        cases = data.get("test_cases", [])
        if not cases:
            break
            
        for case in cases:
            # Storing by ID for easy delta comparison
            test_cases[str(case["id"])] = case
            
        page += 1
        
    return test_cases

def load_previous_state():
    if os.path.exists(PREVIOUS_STATE_FILE):
        with open(PREVIOUS_STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_current_state(state):
    with open(PREVIOUS_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def generate_report_markdown(added, modified, deleted, current_state):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    report_filename = f"{REPORTS_DIR}/browserstack_report_{today}.md"
    
    with open(report_filename, "w") as f:
        f.write(f"# Weekly BrowserStack Test Cases Report ({today})\n\n")
        f.write(f"**Total Test Cases:** {len(current_state)}\n\n")
        
        f.write(f"### 📈 Added ({len(added)})\n")
        if not added:
            f.write("- *None*\n")
        for tc_id, tc in added.items():
            f.write(f"- [{tc_id}] {tc.get('name', 'Unknown')}\n")
            
        f.write(f"\n### ✏️ Modified ({len(modified)})\n")
        if not modified:
            f.write("- *None*\n")
        for tc_id, tc in modified.items():
            f.write(f"- [{tc_id}] {tc.get('name', 'Unknown')}\n")
            
        f.write(f"\n### 🗑️ Deleted ({len(deleted)})\n")
        if not deleted:
            f.write("- *None*\n")
        for tc_id in deleted:
            f.write(f"- [{tc_id}] (Removed from BrowserStack)\n")
            
    return report_filename

def send_slack_notification(added_count, modified_count, deleted_count, total_count):
    if not SLACK_WEBHOOK_URL:
        print("Warning: SLACK_WEBHOOK_URL not set. Skipping Slack notification.")
        return
        
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    message = {
        "text": f"📊 *BrowserStack Weekly Test Cases Update ({today})*\n\n"
                f"• *Total Test Cases:* {total_count}\n"
                f"• *Added:* {added_count}\n"
                f"• *Modified:* {modified_count}\n"
                f"• *Deleted:* {deleted_count}\n\n"
                f"_Check the latest Pull Request for the detailed markdown report._"
    }
    
    response = requests.post(SLACK_WEBHOOK_URL, json=message)
    if response.status_code != 200:
        print(f"Error sending Slack message: {response.text}")
    else:
        print("Slack notification sent successfully.")

def main():
    print("Fetching BrowserStack Project...")
    project_id = fetch_project_id()
    
    print(f"Fetching Test Cases for Project {project_id}...")
    current_state = fetch_all_test_cases(project_id)
    
    print("Loading previous state...")
    previous_state = load_previous_state()
    
    print("Calculating diff...")
    added = {}
    modified = {}
    deleted = []
    
    # Check for Added and Modified
    for tc_id, tc_data in current_state.items():
        if tc_id not in previous_state:
            added[tc_id] = tc_data
        else:
            # Assuming 'updated_at' is the field. Adjust if BrowserStack uses a different case.
            old_updated = previous_state[tc_id].get("updated_at")
            new_updated = tc_data.get("updated_at")
            if str(old_updated) != str(new_updated):
                modified[tc_id] = tc_data
                
    # Check for Deleted
    for tc_id in previous_state.keys():
        if tc_id not in current_state:
            deleted.append(tc_id)
            
    print(f"Diff results: {len(added)} Added, {len(modified)} Modified, {len(deleted)} Deleted.")
    
    print("Generating Markdown Report...")
    report_file = generate_report_markdown(added, modified, deleted, current_state)
    print(f"Report saved to {report_file}")
    
    if added or modified or deleted:
        print("Sending Slack Notification...")
        send_slack_notification(len(added), len(modified), len(deleted), len(current_state))
        
        print("Saving new state...")
        save_current_state(current_state)
    else:
        print("No changes detected this week. Skipping state update and Slack notification.")

if __name__ == "__main__":
    main()
