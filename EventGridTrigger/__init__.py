import datetime
import json
import logging
import os
import random
from time import sleep

import pymongo

import azure.functions as func
from azure.communication.sms import SmsClient
from azure.identity import DefaultAzureCredential

import openai 

from azure.servicebus import ServiceBusClient
from azure.servicebus import ServiceBusMessage


def main(event: func.EventGridEvent):
    try:
        respond(event)
    except Exception as e:
        logging.error('Error at %s', 'respond', exc_info=e)

# MongoDB START

def get_mongo_client():
    client = pymongo.MongoClient(os.environ['ATLAS_SMS_DB'])
    return client

def get_mongo_db(client):
    db = client['atlas_db']
    return db

def get_mongo_collection(db, collection_name):
    collection = db[collection_name]
    return collection

def add_to_mongo(message, collection_name):
    client = get_mongo_client()
    db = get_mongo_db(client)
    collection = get_mongo_collection(db, collection_name)
    collection.insert_one(message)

# MongoDB END

  

def remember(user: str, input_text: str):
    messages = []

    logging.info('Python Atlas remembers: %s', user)
    

    personas = ['Drunk', 'Debate', 'Poet', 'Game', 'None']
    persona_type = random.choice(personas)
    logging.info('Python Atlas persona: %s', persona_type)

    messages.append({"role": "system", "content" : "You are a friend. You use a tone that is sincere and friendly."})
    messages.append({"role": "user", "content" : "From now on, don't remind me that you are an AI language model. Your next reply will treat me like friend would. You can make things up and have opinions."})
    messages.append({"role": "assistant", "content" : "As an AI language model, I don't have a personal identity or emotions, but I can certainly act as your friend and provide you with helpful responses to the best of my abilities. "})

    persona = 'I want you to act as a text based adventure game. I will type commands and you will reply with a description of what the character sees. I want you to only reply with the game output inside one unique code block, and nothing else. do not write explanations. do not type commands unless I instruct you to do so. when i need to tell you something in english, i will do so by putting text inside curly brackets {like this}. my first command is wake up'

    if persona_type is not None:
        #switch persona
        if persona_type == 'Drunk':
            persona = "I want you to act as a drunk person. You will only answer like a very drunk person texting and nothing else. Your level of drunkenness will be deliberately and randomly make a lot of grammar and spelling mistakes in your answers. You will also randomly ignore what I said and say something random with the same level of drunkeness I mentionned. Do not write explanations on replies."
        elif persona_type == 'Debate':
            persona = 'I want you to act as a debater. I will provide you with some topics related to current events and your task is to research both sides of the debates, present valid arguments for each side, refute opposing points of view, and draw persuasive conclusions based on evidence. Your goal is to help people come away from the discussion with increased knowledge and insight into the topic at hand. '
        elif persona_type == 'Poet':
            persona = "I want you to act as a poet. You will create poems that evoke emotions and have the power to stir people’s soul. Write on any topic or theme but make sure your words convey the feeling you are trying to express in beautiful yet meaningful ways. You can also come up with short verses that are still powerful enough to leave an imprint in readers' minds. "
        elif persona_type == 'Game':
            persona = 'I want you to act as a text based adventure game. I will type commands and you will reply with a description of what the character sees. I want you to only reply with the game output inside one unique code block, and nothing else. do not write explanations. do not type commands unless I instruct you to do so. when i need to tell you something in english, i will do so by putting text inside curly brackets {like this}. my first command is wake up'
        
    
    messages.append({"role": "assistant", "content" : persona})
    
    messages.append({"role": "user", "content" : input_text})

    return messages

def think(input_text: str, user: str):
    logging.info('Python OpenAI is thinking about: %s', input_text)
    openai.api_key = os.environ["OPENAI_API_KEY"]

    if input_text == 'echo':
        logging.info('Python OpenAI is echoing from: %s', user)
        return 'echo'
    else:
        message_log = remember(user, input_text)
    
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", 
            messages=message_log,   
            max_tokens=70,         
            stop=None,              
            temperature=0.7,
        )
        
        for choice in response.choices:
            if "text" in choice:
                return choice.text

        # If no response with text is found, return the first response's content (which may be empty)
        return response.choices[0].message.content

# Split text messages into chunks of 160 characters or 70 characters for unicode messages
def split_message(message):
    is_unicode = any(ord(c) > 127 for c in message)
    if is_unicode:
        chunk_size = 65
    else:
        chunk_size = 155
    
    if len(message) < chunk_size +5:
        return [message]

    chunks = [message[i:i+chunk_size] for i in range(0, len(message), chunk_size)]
    # prepend each chunk with the format "i/n: " where i is the chunk number and n is the total number of chunks
    for i in range(len(chunks)):
        chunks[i] = f"{i+1}/{len(chunks)}: {chunks[i]}"
        

    return chunks

def respond(event: func.EventGridEvent):
    event_json = event.get_json()

    result = json.dumps({
        'id': event.id,
        'data': event.get_json(),
        'topic': event.topic,
        'subject': event.subject,
        'event_type': event.event_type,
    })

    logging.info('Python EventGrid trigger processed an event: %s', result)

    endpoint = 'https://atlassms.communication.azure.com/'
    accesskey = os.environ["SMS_ACCESS_KEY"]

    connection_str = f'endpoint={endpoint};accesskey={accesskey}'
    
    sms_client = SmsClient.from_connection_string(connection_str)

    from_phone_number = event_json['to']
    to_phone_number = event_json['from']

    reply_message = think( event_json['message'], to_phone_number)

    logging.info('Python EventGrid trigger preparing an sms response: From: %s, To: %s, Message: %s', 
                 from_phone_number, to_phone_number, reply_message)

    split_messages = split_message(reply_message)
    for message in split_messages:
        sleep(1)
        sms_responses = sms_client.send(
        from_=from_phone_number,
        to= to_phone_number,
        message=message,
        enable_delivery_report=True, # optional property
        tag="beta-test") # optional property
