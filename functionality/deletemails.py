from SA import ServiceAuth

def delete_mail(senders, amount = 0):
  
  serviced = ServiceAuth()
  service = serviced.check_credentials()




  sender_query = " OR ".join(f"from:{s}" for s in senders)
  query = f"{sender_query}" 

  results = []
  request = service.users().messages().list(userId="me", q=query, maxResults = 500)

  while request is not None:
     message_response = request.execute()
     results.extend(message_response.get("messages", []))
     

     if amount and len(results) >= amount:
        results = results[:amount]
        break

     request = service.users().messages().list_next(request, message_response)


##Since there is the option to put multiple senders this needs to be adjusted for that 
  if not results:
    print("Could not find any mail from this sender")
    return

  count_emails = 0

  try:
    for result in results :
      service.users().messages().trash(userId="me", id=result['id']).execute()
      count_emails += 1
  except Exception as err:
        print(f"You have the following error {err}, {type(err)=} : Please try again")     
  else:
    print(f'Successfully deleted {count_emails} emails from {senders}')
