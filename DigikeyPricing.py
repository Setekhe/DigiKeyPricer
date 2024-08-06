
import requests
import json
import os
import sys
import pandas as pd
import re
import urllib.parse as urlparse
import math

#python3 DigikeyPricing.py "Bill Of Materials PowerPortMax-v5.csv" 50

#client data template
client_data_template = {'client_id':'0','client_secret':'0'}

#aggregate functions
agg_functions = {'Value': 'first', 'Quantity': 'sum'}
#API pricing variables
logged_in = False
missing_components = []
total_cost = 0
out_of_stock_cost = 0
common_deliminators = [",","_","-"," ","/","~"]
swaps = 0
#token api url
url = 'https://api.digikey.com/v1/oauth2/token'
df = {}
#This script takes 2 arguments
if len(sys.argv)== 3:
    if not sys.argv[2].isdigit():
        sys.exit("\n The second argument must be a positive integer > 0.")
    try:
        df = pd.read_csv(sys.argv[1])
    except:
        sys.exit("\n The first argument must be a string. It must be the name of the CSV formatted BOM file located in the same folder as this is being run, or be the path to the file.")
    try:
        df = df[['Quantity','Value','Stock Code']]
    except:
        sys.exit("\n The BOM file is malformed and needs to contain one \'Quantity\' column, one \'Stock Code\' column and one \'Value\' column.")
    if not (df['Quantity'].dtype=='int32' or df['Quantity'].dtype=='int64'):
        print(df['Quantity'])
        sys.exit("\n The Quantity column must only contains integers")
    if not (df['Stock Code'].dtype=='object' and df['Value'].dtype=='object'):
        sys.exit("\n The Stock Code and Value column must only contains objects e.g. strings.")
    #manipulate the data as needed
    df['Quantity']*=int(sys.argv[2])
    #NO FIT conditions
    nfcon = df['Stock Code'].str.contains(r'\d', regex=True)
    nfdf = df[~nfcon]
    df = df[nfcon] 
    #Assume stock codes are truth axioms
    df = df.groupby(df['Stock Code']).aggregate(agg_functions).reset_index()
    df = pd.concat([df, nfdf], ignore_index=True).reset_index()
else:
    sys.exit("\n The script takes two inputs, a string containing the name of the BOM file, and a positive integer representing how many sets are desired.")




#login via credential file
if True:
    creds_file = 'credentials.json'
    try:
        # Try to open the credentials file in read mode
        with open(creds_file, 'r') as cred_data:
            # Attempt to load JSON data from the file
            creds = json.load(cred_data)  
        # Check if 'client_id' key exists in the loaded JSON
        if 'client_id' not in creds:
            # Open the credentials file in write mode to update it
            with open(creds_file, 'w') as cred_data:
                json.dump(client_data_template, cred_data)
    except (FileNotFoundError, json.JSONDecodeError):
        # If the file does not exist or JSON is invalid, create or overwrite the file
        with open(creds_file, 'w') as cred_data:
            json.dump(client_data_template, cred_data)
        

    #handle the response and save 
    while logged_in == False:
        with open(creds_file, 'r') as cred_data:
            creds = json.load(cred_data)  
        #required data for token request
        url_data = {
        'client_id': creds['client_id'],
        'client_secret': creds['client_secret'],
        'grant_type': 'client_credentials'
        }
        response = requests.post(url, data=url_data)
        if response.status_code == 200:
            response_data = response.json()
            code = response_data['access_token']
            logged_in = True
            client_id = creds['client_id']
        elif response.status_code == 401:
            creds['client_id'] = input("\n Please (re)type your client id:\n")
            creds['client_secret'] = input("\n Please (re)type your client secret:\n")
            with open(creds_file, 'w') as cred_data:
                json.dump(creds, cred_data)
#login via environment variables
else:
    while logged_in == False:
        url_data = {
        'client_id': str(os.environ['DIGIKEY_CLIENT_ID']),
        'client_secret': str(os.environ['DIGIKEY_CLIENT_SECRET']),
        'grant_type': 'client_credentials'
        }
        response = requests.post(url, data=url_data)
        if response.status_code == 200:
            response_data = response.json()
            code = response_data['access_token']
            logged_in = True
            client_id = str(os.environ['DIGIKEY_CLIENT_ID'])
        elif response.status_code == 401:
            blank = input(" Your enviornment variables are set incorrectly.\n DIGIKEY_CLIENT_ID must contian your client id and DIGIKEY_CLIENT_SECRET must contain your client secret.\n Restart your CLI once you have changed them.\n")

    
def totalup (row, data):
    quantity = int(row['Quantity'])
    break_reels = []
    #math.ceil(((float(break_cuts[i-1]['UnitPrice'])*int(break_cuts[i-1]['BreakQuantity']))*100))/100
    #if both reels and cuts exist
    if(len(data["Products"])>1):
        break_reels = list(reversed(data["Products"][0]['StandardPricing']))
        break_cuts = list(reversed(data["Products"][1]['StandardPricing']))
    else: #only save cuts
        break_cuts = list(reversed(data["Products"][0]['StandardPricing']))
    bva = 0
    bvb = 0
    bvc = 0
    #if their are no reel options or they are out of stock, only use cuts
    if break_reels == [] or (data["Products"][0]["StockNote"] != "In Stock" and data["Products"][1]["StockNote"] == "In Stock"):
        bva, row['Quantity'] = breakcutloop(break_cuts, quantity)
        if len(data["Products"][0]["PackageTypes"])==1:
            print(" should be acquired by purchasing " +str(row['Quantity'])+" units of "+ data["Products"][0]["PackageTypes"][0])
        else:
            print(" should be acquired by purchasing " +str(row['Quantity'])+" units of "+ data["Products"][0]["PackageTypes"][1])
        return bva, row
    #else in the case that everything is available or completely out of stock
    else:
        if break_reels[0]['BreakQuantity']<= quantity:
            i=0
            while i*break_reels[-1]['BreakQuantity']<quantity:
                i+=1
            # Unit Price * one over needed reels
            bvb = math.ceil(((float(break_reels[0]['UnitPrice']*(i)*break_reels[-1]['BreakQuantity']))*100))/100
            #cut calculator
            break_cut_cost, quantity = breakcutloop (break_cuts, (quantity - (break_reels[-1]['BreakQuantity']*(i-1))))
            quantity = quantity + break_reels[0]['BreakQuantity']*(i-1)
            #make up difference with cuts
            bva = math.ceil(((float(break_reels[0]['UnitPrice']*(i-1)*break_reels[-1]['BreakQuantity']))*100))/100 + break_cut_cost
            if bvb <= bva:
                row['Quantity'] = (i)*break_reels[-1]['BreakQuantity']
                print(" should be acquired by purchasing " +str(row['Quantity'])+" units of Tape & Reel (TR).")
                return bvb, row
            else:
                row['Quantity'] = quantity
                print(" should be acquired by purchasing " +str(break_reels[-1]['BreakQuantity']*(i-1))+" units of Tape & Reel (TR) and "+str(row['Quantity']-break_reels[0]['BreakQuantity']*(i-1))+" units of Cut Tape (CT).")
                return bva, row
        else:
            for i in range(1,len(break_reels)):
                if break_reels[i]['BreakQuantity']<= quantity:
                    j=0
                    while j*break_reels[-1]['BreakQuantity']<quantity:
                        j+=1
                    #an entire break value above
                    bvc = math.ceil(((float(break_reels[i-1]['UnitPrice']*break_reels[i-1]['BreakQuantity']))*100))/100
                    #an extra lot added
                    bvb = math.ceil(((float(break_reels[i]['UnitPrice']*(j)*break_reels[-1]['BreakQuantity']))*100))/100
                    break_cut_cost, quantity = breakcutloop (break_cuts, (quantity - (break_reels[-1]['BreakQuantity']*(j-1))))
                    quantity = quantity + break_reels[-1]['BreakQuantity']*(j-1)
                    #make up difference with cuts
                    bva = math.ceil(((float(break_reels[i]['UnitPrice']*(j-1)*break_reels[-1]['BreakQuantity']))*100))/100 + break_cut_cost
                    if bvc <= bvb and bvc <= bva:
                        row['Quantity'] = break_reels[i-1]['BreakQuantity']
                        print(" should be acquired by purchasing " +str(row['Quantity'])+" units of Tape & Reel (TR).")
                        return bvc, row
                    elif bvb <= bva:
                        row['Quantity'] = (j)*break_reels[-1]['BreakQuantity']
                        print(" should be acquired by purchasing " +str(row['Quantity'])+" units of Tape & Reel (TR).")
                        return bvb, row
                    else:
                        row['Quantity'] = quantity
                        print(" should be acquired by purchasing " +str(break_reels[-1]['BreakQuantity']*(j-1))+" units of Tape & Reel (TR) and"+str(row['Quantity']-break_reels[-1]['BreakQuantity']*(j-1))+" units of Cut Tape (CT).")
                        return bva, row
                
def breakcutloop (break_cuts, quantity):
    if break_cuts[0]['BreakQuantity']<= quantity:
        return math.ceil(((float(break_cuts[0]['UnitPrice'])*int(quantity))*100))/100, quantity
    for i in range(1,len(break_cuts)):
        if break_cuts[i]['BreakQuantity']<= quantity:
            bva = math.ceil(((float(break_cuts[i]['UnitPrice'])*int(quantity))*100))/100
            bvb = math.ceil(((float(break_cuts[i-1]['UnitPrice'])*int(break_cuts[i-1]['BreakQuantity']))*100))/100
            if bvb <= bva:
                quantity = break_cuts[i-1]['BreakQuantity']               
                return bvb, quantity
            else:
                return bva, quantity
                

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
    return pricing_response

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
    DGKNum = search_response.json()['ExactMatches'][0]['ProductVariations'][0]['DigiKeyProductNumber']
    print(" "+row['Stock Code']+" was unresolvable and is being searched for using the DigiKey code of " + DGKNum+ " instead.") 
    
    return(DGKNum)
    
def response_handler(row, pricing_response):
    global total_cost, out_of_stock_cost, swaps
    pricing_data = pricing_response.json()
    #if the response reports an error with the request
    if pricing_response.status_code == 404:
        #if the part isn't found add it to the list of missing item matches
        if 'PART_NOT_FOUND' in pricing_data['title']:
            if any(char in row['Stock Code'] for char in common_deliminators):
                print(" cannot be found. Will attempt with a different deliminator.\n")
                if swaps >= len(common_deliminators):
                    print("\n "+row['Stock Code']+ " cannot be found using any common deliminators.\n")
                    missing_components.append(row)
                    swaps = 0
                    return True, row
                else:
                    for char in common_deliminators:
                        if char in row['Stock Code']:
                            row['Stock Code'] = row['Stock Code'].replace(char, common_deliminators[swaps])
                    swaps += 1
                    return False, row
            else:
                missing_components.append(row)
                print(" cannot be found.")
                return True, row
        #if the manufacturing number doesn't align or is ambigious find the digikey code
        if 'UNRESOLVED_MANF_NUMBER' in pricing_data['title']:
            DGKNum = keywordsearch(row)
            row['Stock Code'] = DGKNum
            return False, row
        else:
            print(pricing_data)
    #if the response reports an error with the request format
    elif pricing_response.status_code == 400:
        #if the quantity must be a multiple of a certain number
        if 'Quantity must be' in pricing_data['title']:
            #calculate what the quantity must be rounded up to
            multiple = int(pricing_data['title'].replace(" "+row['Stock Code'],'').split(" ")[-1])
            row['Quantity']= (int(row['Quantity'])//multiple +1) * multiple
            print(" needs to purchased in multiples of "+str(multiple)+" and so will be purchased at a volume of " +str(row['Quantity'])+".")
            return False, row
        if re.search(r"([A-Za-z]+( [A-Za-z]+)+) '[0-9]+' ([A-Za-z0-9]+( [A-Za-z0-9]+)+)\.",pricing_data['detail']):
            print(" \n The quantity of item "+row['Stock Code']+" is likely too high (e.g. over 2,147,483,647) or is otherwise impossible to process.\n")
            missing_components.append(row)
            return True, row
        else:
            print(pricing_data)
    else:
        cost,row = totalup(row, pricing_data)
        if pricing_data["Products"][0]["StockNote"] != "In Stock":
            if len(pricing_data["Products"])>1:
                if pricing_data["Products"][1]["StockNote"] != "In Stock":
                    print(" "+row['Stock Code'] + " would be purchased at a total of £"+ str(cost)+", but is out of stock.\n")
                    out_of_stock_cost += cost
                    return True, row
                else:
                    print(" "+row['Stock Code'] +" can be purchased for a total of £"+ str(cost)+", but relies on Cut Tape (CT) only as Tape & Reel (TR) is out of stock.\n")
                    total_cost += cost
                    print(" Current total is: " + str(total_cost)+"\n")
                    return True, row
            else:
                print(" "+row['Stock Code'] + " would be purchased at a total of £"+ str(cost)+", but is out of stock.\n")
                out_of_stock_cost += cost
                return True, row
        else:
            print(" "+row['Stock Code'] + " can be purchased for a total of £"+ str(cost)+"\n")
            total_cost += cost
            print(" Current total is: " + str(total_cost)+"\n")
            return True, row
print("\n")
for index, row in df.iterrows():
    complete = False
    swaps = 0
    while complete == False:
        print(" "+row['Stock Code'], end = "")
        pricing_response = priceup(row)
        complete, row = response_handler(row, pricing_response)
    

#end output
if missing_components != []:
    print("\n\n ------------------------------------------\n Miss matching stock codes are as follows:\n")
    for item in missing_components:
        print(" "+getattr(item, 'Stock Code')+" with the attached value of "+getattr(item, 'Value')+"\n")
    print(" ------------------------------------------\n")
print("\n ----------------------------\n The total cost is £{:0.2f}\n ----------------------------\n".format(round(total_cost,2)))
if(out_of_stock_cost>0):
    print("\n --------------------------------------------\n The cost of out of stock items is £{:0.2f}\n --------------------------------------------\n".format(round(out_of_stock_cost,2)))