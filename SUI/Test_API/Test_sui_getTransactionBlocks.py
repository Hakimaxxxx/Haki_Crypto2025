import requests
import json

url = "https://api.blockberry.one/sui/v1/transactions?page=0&size=20&orderBy=DESC&sortBy=AGE"

headers = {"accept": "*/*", "x-api-key": "Y1CcambMPLreF9NiuJ8JeZlfmHqpZY"}

response = requests.post(url, headers=headers)

# Save the response content to a JSON file
with open("response_test_sui_getTransactionBlocks.json", "w", encoding="utf-8") as f:
    f.write(response.text)