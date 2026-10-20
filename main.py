import inquirer
import sys
from inquirer.errors import ValidationError

from functionality.block import block_user, is_valid_email, show_blocked, unblock_user
from functionality.deletemails import delete_mail
from SA import MissingCredentialsError


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


def ask(questions):
    """Run an inquirer prompt and exit cleanly when the user cancels."""
    try:
        answers = inquirer.prompt(questions)
    except KeyboardInterrupt:
        sys.exit()

    if not answers:
        sys.exit()

    return answers


def validate_sender(answers, current):
    """Reject empty sender lists - an empty query would match every message."""
    senders = [part.strip() for part in str(current).split(',') if part.strip()]

    if not senders:
        raise ValidationError(current, "Enter at least one sender address")

    return True


def validate_amount(answers, current):
    """Reject amounts that are not positive whole numbers."""
    try:
        value = int(str(current).strip())
    except (TypeError, ValueError):
        raise ValidationError(current, "Enter a whole number")

    if value < 1:
        raise ValidationError(current, "Enter a number of 1 or more")

    return True


def validate_address(answers, current):
    """Reject anything that is not a valid email address."""
    if not is_valid_email(str(current).strip()):
        raise ValidationError(current, "Enter a valid email address")

    return True


def delete():
    senders = [inquirer.Text('sender',
    message='From what sender(s) do you wish to delete emails from (comma separated, e.g. example_user@gmail.com)',
    validate=validate_sender)]

    answer = ask(senders)
    sender_list = [s.strip() for s in answer['sender'].split(',') if s.strip()]

    if not sender_list:
        print("No sender given, nothing to do.")
        return

    print(f"Will remove emails from : {', '.join(sender_list)}")

    print()
# %%

    amount_options = [
    inquirer.List('options',
    message= 'Choose one of the following: ',
    choices = ['Delete Custom Amount','Delete All']),
]

    answer_amount = ask(amount_options)

    if (answer_amount['options'] =='Delete Custom Amount'):

        custom_amount = [inquirer.Text('amount',
        message='Please enter the amount of emails you wish to remove',
        validate=validate_amount
        )]
        amount = ask(custom_amount)

        final_amount = int(amount['amount'])
        show_final_amount = final_amount
    else:
        final_amount = None
        show_final_amount = 'ALL'


    verification = [
    inquirer.Confirm('verify',
    message= f'Are you sure you wish to remove {show_final_amount} emails from {", ".join(sender_list)}?'),
    ]

    verification_final = ask(verification)

    if(verification_final['verify']):
        delete_mail(sender_list, final_amount)
    else:
        sys.exit()
# %%

def block_accounts():

    option = [
    inquirer.List(
        'options',
             message = 'Choose one of the following: ',
             choices = ['Block', 'Unblock']
        )
    ]

    if ask(option)['options'] == 'Block':

        account = [
            inquirer.Text(
                'block',
                message="What user do you wish to block (enter in the form example_user@gmail.com)?",
                validate=validate_address
            ),
        ]
        answer = ask(account)
        block_user(answer['block'])

    else:
        blocked = show_blocked()

        if not blocked:
            print("There are no blocked accounts.")
            return

        questions = [
            inquirer.Checkbox('accounts',
                            message="Which accounts do you want to unblock?",
                            choices=blocked,
                            ),
        ]

        answers = ask(questions)
        selected = answers.get('accounts') or []

        if not selected:
            print("Nothing selected, nothing to unblock.")
            return

        unblock_user(selected)

actions = {
    'Delete Emails': delete,
    'Block Accounts' : block_accounts
}


def main():
    prompt = [
        inquirer.List('options',
                      message= 'What would you like to do?',
                      choices= ['Delete Emails', 'Block Accounts']),
    ]

    actions[ask(prompt)['options']]()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit()
    except MissingCredentialsError as err:
        print(err)
        sys.exit(1)
    except Exception as err:
        print(f"\nSomething went wrong: {err}")
        sys.exit(1)
