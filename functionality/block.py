from SA import ServiceAuth
from googleapiclient.errors import HttpError
from email_validator import validate_email, EmailNotValidError

def is_valid_email(email):
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False

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
        except HttpError as error:
            print(f"An error occurred: {error}")
        except Exception as err:
            print(f"You have the following error {err}, {type(err)=} : Please try again")  
        else:
            print(f"Successfully blocked")
        return filter_content.get("id")
    
    else:
        print("Not a valid email address")

    

def show_blocekd():
    pass


#Store filtered emails and stuff in a JSON file.