import requests
import json
import os
import sys
import pandas as pd
import re
import urllib.parse as urlparse
import math

#cd Documents/DigiKeyBOM
#python3 DigikeyPricing.py "Bill Of Materials PowerPortMax-v5.csv" 50
client_id = str(os.environ['DIGIKEY_CLIENT_ID'])
client_secret = str(os.environ['DIGIKEY_CLIENT_SECRET'])
df = pd.read_csv(sys.argv[1])

#manipulate the data as needed
df['Quantity']*=int(sys.argv[2])
df = df[['Quantity','Value','Stock Code']]
nfcon = (df['Stock Code']=='nf') | (df['Stock Code']=='NO FIT')
nfdf = df[nfcon]
df = df[~nfcon] 
agg_functions = {'Value': 'first', 'Quantity': 'sum'}
df = df.groupby(df['Stock Code']).aggregate(agg_functions).reset_index()
df = pd.concat([df, nfdf], ignore_index=True).reset_index()

missing_components = []
total_cost = 0

#token api url
url = 'https://api.digikey.com/v1/oauth2/token'
#required data for token request
url_data = {
    'client_id': client_id,
    'client_secret': client_secret,
    'grant_type': 'client_credentials'
}
#handle the response and save 
response = requests.post(url, data=url_data)
if response.status_code == 200:
    response_data = response.json()
    code = response_data['access_token']
    
def totalup (data):
    quantity = pricing_data["Products"][0]['RecommendedQuantity']
    break_values = pricing_data["Products"][0]['StandardPricing']
    for break_value in reversed(break_values):
        if break_value['BreakQuantity']<= quantity:
            return math.ceil(((float(break_value['UnitPrice'])*int(quantity))*100))/100

        
    

def priceup (row,alt = "0"):
    #use the expected stock code
    if alt == "0":
        pricing_url = 'https://api.digikey.com/products/v4/search/packagetypebyquantity/'+urlparse.quote(row['Stock Code'],safe='')
    #search using a specific term (usually when digikey num is needed)
    else:
        pricing_url = 'https://api.digikey.com/products/v4/search/packagetypebyquantity/'+urlparse.quote(alt,safe='')
    pricing_header = {
        'X-DIGIKEY-Client-Id': client_id,
        'Authorization': 'Bearer '+code,
        'X-DIGIKEY-Locale-Site': 'UK',
        'X-DIGIKEY-Locale-Currency': 'GBP'
    }
    pricing_data = {
        'requestedQuantity' : int(row['Quantity'])
    }
    pricing_response = requests.get(pricing_url, headers=pricing_header, params=pricing_data)
    pricing_data = pricing_response.json()
    return pricing_response, pricing_data

def keywordsearch(row):
    search_url = 'https://api.digikey.com/products/v4/search/keyword'
    search_header = {
        'X-DIGIKEY-Client-Id': client_id,
        'Authorization': 'Bearer '+code,
        'X-DIGIKEY-Locale-Site': 'UK',
        'X-DIGIKEY-Locale-Currency': 'GBP'
    }
    #return the first result after searching for the specific stock code
    search_data = {
        "Keywords": row['Stock Code'],
        "Limit": "1"
    }
    search_response = requests.post(search_url, headers=search_header, json=search_data)
    #return the first digikey number of the first exact match of the product
    return(search_response.json()['ExactMatches'][0]['ProductVariations'][0]['DigiKeyProductNumber'])
    


for index, row in df.iterrows():
    pricing_response, pricing_data = priceup(row)
    #if the response reports an error with the request
    if pricing_response.status_code == 404:
        #if the part isn't found add it to the list of missing item matches
        if 'PART_NOT_FOUND' in pricing_data['title']:
            missing_components.append(row)
        #if the manufacturing number doesn't align or is ambigious find the digikey code
        elif 'UNRESOLVED_MANF_NUMBER' in pricing_data['title']:
            DGKNum = keywordsearch(row)
            pricing_response, pricing_data = priceup(row,DGKNum)
            try:
                total_cost += totalup(pricing_data)
            except:
                print("AA")
        else:
            print(pricing_data)
    #if the response reports an error with the request format
    elif pricing_response.status_code == 400:
        #if the quantity must be a multiple of a certain number
        if 'Quantity must be' in pricing_data['title']:
            #calculate what the quantity must be rounded up to
            multiple = int(pricing_data['title'].replace(" "+row['Stock Code'],'').split(" ")[-1])
            row['Quantity']= (int(row['Quantity'])//multiple +1) * multiple
            #retry the pricing
            pricing_response, pricing_data = priceup(row)
            try:
                total_cost += totalup(pricing_data)
            except:
                print("BB")
    else:
        try:
            total_cost += totalup(pricing_data)
        except:
            print("CC")

print("\nMiss matching stock codes are as follow:\n")
for item in missing_components:
    print(getattr(item, 'Stock Code')+" with the attached value of "+getattr(item, 'Value')+"\n")
print("\nThe total cost is £{:0.2f}".format(round(total_cost,2)))