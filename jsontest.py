import json
import re



def load_json_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:

        test = json.load(f)

        new_dict = {'emails': [entry['email'] for entry in list(test.values())[0]]} ## Gets all emails into one single dict with key : emails 

        return new_dict


def main():    

    file_path = 'blocked.json'
    json_data = load_json_data(file_path)
    
    
    emails = []

    for k in json_data['emails']:
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

    
write_data("mathiasolofeinarljungberg@gmail.com")
