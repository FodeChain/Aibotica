# encoding: utf-8
import uuid
import time
import requests
from auth_util import gen_sign_headers
from prompt import *

# 请替换APP_ID、APP_KEY
APP_ID = '2025616291'
APP_KEY = 'hbmjeLcnaLRuGKNp'
URI = '/vivogpt/completions'
DOMAIN = 'api-ai.vivo.com.cn'
METHOD = 'POST'

def sync_vivogpt(prompt,input_text):
    params = {
        'requestId': str(uuid.uuid4())
    }
    #print('requestId:', params['requestId'])

    data = {
        #'prompt': Planner_prompt ,
        'model': 'vivo-BlueLM-TB-Pro',
        'sessionId': str(uuid.uuid4()),
        'extra': {
            'temperature': 0.9
        },
        "systemPrompt": prompt,
        "messages": [
            #{    
            #    "role": "system",
            #    "content": prompt,
            #},
            {    
                "role": "user",
                "content": input_text,
            }
        ]
    }
    headers = gen_sign_headers(APP_ID, APP_KEY, METHOD, URI, params)
    headers['Content-Type'] = 'application/json'

    start_time = time.time()
    url = 'https://{}{}'.format(DOMAIN, URI)
    response = requests.post(url, json=data, headers=headers, params=params)

    if response.status_code == 200:
        res_obj = response.json()
        print(f'response:{res_obj}')
        if res_obj['code'] == 0 and res_obj.get('data'):
            content = res_obj['data']['content']
            print(f'final content:\n{content}')
            end_time = time.time()
            timecost = end_time - start_time
            print('请求耗时: %.2f秒' % timecost)
            return content
    else:
        print(response.status_code, response.text)
        #return response.status_code
    end_time = time.time()
    timecost = end_time - start_time
    print('请求耗时: %.2f秒' % timecost)

'''
if __name__ == '__main__':
    input_text =
    
    a=sync_vivogpt(Assembler_prompt,input_text)
    print(a)
'''