import inquirer
import sys
from functionality.deletemails import delete_mail
from functionality.block import block_user


print(r""" ___  _        __ _ ____  _____ 
 / _ \| | ___  / _/ |___ \|___ / 
| | | | |/ _ \| |_| | __) | |_ \ 
| |_| | | (_) |  _| |/ __/ ___) |
 \___/|_|\___/|_| |_|_____|____/                  
""")
print("\n****************************************************************")
print("\n*This project is just for fun and not meant to be taken seriously, security risks are at your own responsibility.*")
print("\n*All source code is available at https://github.com/Olof123-hash/gmail-remover*")
print("\n****************************************************************\n")

def delete():
    senders = [inquirer.Text('sender', 
    message='From what sender(s) do you wish to delete emails from (in the form example_user or example_user@gmail.com1)')]

    answer = inquirer.prompt(senders)
    sender_list = [s.strip() for s in answer['sender'].split(',') if s.strip()]
    
    print(f"Will remove emails from : {', '.join(sender_list)}")
    
    print()
# %%
    
    amount_options = [
    inquirer.List('options',
    message= 'Choose one of the following: ', 
    choices= ['Delete Custom Amount','Delete All']),
]

    answer_amount = inquirer.prompt(amount_options)

    if (answer_amount['options'] =='Delete Custom Amount'):

        custom_amount = [inquirer.Text('amount',
        message='Please enter the amount of emails you wish to remove'
        '')]
        amount = inquirer.prompt(custom_amount)

        final_amount = int(amount['amount'])
        show_final_amount = final_amount
        ##need to add validation here 
    else:
        final_amount = None
        show_final_amount = 'ALL'
   

    verification = [
        inquirer.Confirm('verify',
        message= [f'Are you you wish to remove {show_final_amount} emails from {', '.join(sender_list)}']),
    ]

    verification_final = inquirer.prompt(verification)

    if(verification_final['verify']):
        delete_mail(sender_list, final_amount)
    else:
        sys.exit()
# %%
def manage_subscription():
    pass

def block_accounts():

    option = [
        inquirer.List(
            'options',
             message = 'Choose one of the following: ',
             choices = ['Block', 'Unblock']
        )
    ]

    if inquirer.prompt(option)['options']:
    
        account = [
            inquirer.Text(
                'block',
                message="What user do you wish to block (enter in the form example_user@gmail.com)?"
            ),
        ]
        answer = inquirer.prompt(account)
        block_user((answer['block']))

        #Do validation here the same way with the amount of email validation that its rendered on the inquirer function so that the prompt can repeat itself

    else:
            pass

actions = {
    'Delete Emails': delete,
    'Manage Subscriptions': manage_subscription,
    'Block Accounts' : block_accounts
}
prompt = [
    inquirer.List('options',
                  message= 'What would you like to do?', 
                  choices= ['Delete Emails', 'Manage Subscriptions', 'Block Accounts']),
]

actions[inquirer.prompt(prompt)['options']]()


