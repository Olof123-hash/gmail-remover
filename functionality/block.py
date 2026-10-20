from SA import ServiceAuth
from googleapiclient.errors import HttpError
from email_validator import validate_email, EmailNotValidError
import json
import inquirer
import re


def is_valid_email(email):
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False

def show_blocked():

    with open('blocked.json', 'r', encoding='utf-8') as f:
    
            test = json.load(f)
    
            new_dict = {'emails': [entry['email'] for entry in list(test.values())[0]]} ## Gets all emails into one single dict with key : emails 
    
            emails = []

            for k in new_dict['emails']:
                 emails.append(k)
            
    return emails

def write_data(email):
    with open('blocked.json', 'r') as f:
            data = json.load(f)
    
    existing = {entry['email'] for entry in data['blockedAddresses']}
    if email not in existing:
            data['blockedAddresses'].append({"email": email})
    
    with open("blocked.json", "w") as f:
            json.dump(data, f, indent=4)

def block_user(email):

    serviced = ServiceAuth()
    service = serviced.check_credentials()

    filter_content = {
                    'criteria': {
                        'from': email
                    },
                    'action': {
                        'addLabelIds': ['TRASH'],
                        'removeLabelIds': ['INBOX', 'UNREAD'],
                    },
                }
    
    filter = (
    service.users()
    .settings()
    .filters()
    .create(
    userId="me", body=filter_content
    )
    )

  
    if is_valid_email(email):

        try:
            filter.execute()
            write_data(email)
        except HttpError as error:
            print(f"An error occurred: {error}")
        except Exception as err:
            print(f"You have the following error {err}, {type(err)=} : Please try again")  
        else:
            print(f"Successfully blocked")
        return filter_content.get("id")
    
    else:
        print("Not a valid email address")

    
def unblock_user():
     pass





#Store filtered emails and stuff in a JSON file.